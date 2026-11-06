"""Generated account credentials and one-time encrypted delivery to the creator."""
import base64
import hashlib
import json
import secrets
import string
import time
from flask import current_app,session,abort
from cryptography.fernet import Fernet
from .security import connect,credential_fingerprint
from .db import query_one


def init_credentials():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS issued_credentials(
            token TEXT PRIMARY KEY,actor_user_id INTEGER NOT NULL,payload TEXT NOT NULL,expires REAL NOT NULL)''')


def temporary_password():
    alphabet=string.ascii_letters+string.digits+'!@#$%*?'
    while True:
        value=''.join(secrets.choice(alphabet) for _ in range(16))
        if all((any(c.isupper() for c in value),any(c.islower() for c in value),any(c.isdigit() for c in value),any(c in '!@#$%*?' for c in value))):return value


def faculty_id():
    while True:
        code='FAC-'+secrets.token_hex(4).upper()
        if not query_one('SELECT user_id FROM users WHERE username=:code',{'code':code}) and not query_one('SELECT teacher_id FROM teachers WHERE faculty_code=:code',{'code':code}):return code


def cipher():return Fernet(base64.urlsafe_b64encode(hashlib.sha256(current_app.secret_key.encode()).digest()))


def issue(user_id,username,password,password_hash):
    token=secrets.token_urlsafe(32)
    payload=dict(user_id=user_id,username=username,password=password,fingerprint=credential_fingerprint(password_hash))
    encrypted=cipher().encrypt(json.dumps(payload).encode()).decode()
    with connect() as db:
        db.execute('DELETE FROM issued_credentials WHERE expires<? OR actor_user_id=?',(time.time(),session['user_id']))
        db.execute('INSERT INTO issued_credentials VALUES(?,?,?,?)',(token,session['user_id'],encrypted,time.time()+600))
    session['issued_credential']=token


def reveal():
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record=db.execute('SELECT * FROM issued_credentials WHERE token=? AND actor_user_id=? AND expires>?',
            (session.get('issued_credential',''),session['user_id'],time.time())).fetchone()
        if not record:return None
        data=json.loads(cipher().decrypt(record['payload'].encode()))
        user=query_one('SELECT user_id,username,password_hash FROM users WHERE user_id=:id',{'id':data['user_id']})
        if not user or user['username']!=data['username'] or credential_fingerprint(user['password_hash'])!=data['fingerprint']:return None
        db.execute('DELETE FROM issued_credentials WHERE token=?',(record['token'],))
    session.pop('issued_credential',None)
    return data
