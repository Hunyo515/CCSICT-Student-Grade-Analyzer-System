"""Durable, single-host authentication controls shared across WSGI workers."""
from contextlib import contextmanager
import hashlib
import json
import hmac
import secrets
import sqlite3
import time
from pathlib import Path

from flask import abort, current_app, request, session, g, redirect, url_for


@contextmanager
def connect():
    conn = sqlite3.connect(current_app.config['SECURITY_DB'], timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_security(app):
    if len(app.config.get('SECRET_KEY', '')) < 32 or app.config['SECRET_KEY'].startswith('change-me'):
        raise RuntimeError('Set SECRET_KEY to a random secret of at least 32 characters.')
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get('SECURITY_DB'):
        app.config['SECURITY_DB'] = str(Path(app.instance_path) / 'security.sqlite3')
    with app.app_context(), connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER, credential TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS previews (token TEXT PRIMARY KEY, user_id INTEGER, payload TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, count INTEGER, expires REAL);
        ''')
    app.jinja_env.globals['csrf_token'] = csrf_token


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def rate_limit(key, limit=5, seconds=900):
    key = hashlib.sha256(key.encode()).hexdigest()
    now = time.time()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM attempts WHERE expires <= ?', (now,))
        row = db.execute('SELECT count, expires FROM attempts WHERE key=?', (key,)).fetchone()
        if row and row['count'] >= limit:
            retry = max(1, int(row['expires'] - now))
        else:
            db.execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now + seconds))
            retry = None
    if retry:
        from werkzeug.exceptions import TooManyRequests
        raise TooManyRequests(description=f'Too many attempts. Try again in {retry} seconds.', retry_after=retry)


def protect_request():
    if request.method != 'POST':
        return
    if not session.get('csrf') or not hmac.compare_digest(session['csrf'].encode(), request.form.get('csrf_token', '').encode()):
        abort(400, description='This form expired. Go back, reload the page, and try again.')
    if request.blueprint == 'auth':
        rate_limit('auth-ip:' + (request.remote_addr or 'unknown'), current_app.config.get('AUTH_IP_LIMIT', 1200), current_app.config.get('AUTH_IP_WINDOW', 900))
        if request.endpoint == 'auth.login':
            rate_limit('login-account:' + request.form.get('username', '').strip().lower(), 5)


def store_preview(data):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("DELETE FROM previews WHERE expires <= ? OR user_id=?", (time.time(), session["user_id"]))
        db.execute("INSERT INTO previews VALUES (?,?,?,?)", (token, session["user_id"], json.dumps(data), time.time()+900))
    session["csv_preview"] = token


def load_preview(consume=False):
    token = session.get("csv_preview")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload FROM previews WHERE token=? AND user_id=? AND expires>?", (token, session["user_id"], time.time())).fetchone()
        if consume:
            db.execute("DELETE FROM previews WHERE token=? AND user_id=?", (token, session["user_id"]))
            session.pop("csv_preview", None)
    return json.loads(row["payload"]) if row else None


def credential_fingerprint(password_hash):
    return hmac.new(current_app.secret_key.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


def create_session(user):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires <= ?", (time.time(),))
        db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["user_id"], credential_fingerprint(user["password_hash"]+'|'+(user.get('email') or '')), time.time()+1800))
    session["auth_token"] = token


def revoke_session():
    token = session.get("auth_token", "")
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))


def validate_session():
    if not session.get("user_id") or request.endpoint == "static":
        return
    from .db import query_one
    token = hashlib.sha256(session.get("auth_token", "").encode()).hexdigest()
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE token=? AND expires>?", (token, time.time())).fetchone()
    user = query_one("SELECT user_id, role, status, password_hash, email,must_change_password FROM users WHERE user_id=:id", {"id": session["user_id"]}) if row else None
    valid = bool(user and row["user_id"] == user["user_id"] and user["status"] == "ACTIVE" and user["role"] == session.get("role") and hmac.compare_digest(row["credential"], credential_fingerprint(user["password_hash"]+'|'+(user.get('email') or ''))))
    if valid and user["role"] in ("student", "faculty"):
        table, key = ("students", "student_id") if user["role"] == "student" else ("teachers", "teacher_id")
        profile = query_one(f"SELECT {key}, status FROM {table} WHERE user_id=:id", {"id": user["user_id"]})
        valid = bool(profile and profile["status"] == "ACTIVE" and profile[key] == session.get(key))
    if not valid:
        revoke_session()
        session.clear()
        return redirect(url_for("auth.select_role"))
    with connect() as db:
        db.execute("UPDATE sessions SET expires=? WHERE token=?", (time.time()+1800, token))
    if user.get('must_change_password') and user['role']!='faculty' and request.endpoint not in ('auth.change_password','auth.logout','static'):
        return redirect(url_for('auth.change_password'))
