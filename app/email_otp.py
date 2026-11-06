"""Email login challenge. Codes are never returned to the browser or logs."""
import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from flask import current_app, session
from .security import connect, rate_limit, credential_fingerprint


def init_otp():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS email_challenges (
            token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,digest TEXT NOT NULL,
            credential TEXT NOT NULL,expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL)''')


def digest(token,code):
    return hmac.new(current_app.secret_key.encode(),(token+':'+code).encode(),hashlib.sha256).hexdigest()


def send_code(address,code):
    cfg=current_app.config
    if not cfg.get('MAIL_HOST') or not cfg.get('MAIL_FROM'):
        raise RuntimeError('Email delivery is not configured. Contact the system owner.')
    msg=EmailMessage();msg['Subject']='Your CCSICT sign-in code';msg['From']=cfg['MAIL_FROM'];msg['To']=address
    msg.set_content(f'Your CCSICT sign-in code is {code}. It expires in 5 minutes. Do not share this code. If you did not sign in, ignore this message.')
    cls=smtplib.SMTP_SSL if cfg.get('MAIL_SSL') else smtplib.SMTP
    kwargs={'host':cfg['MAIL_HOST'],'port':cfg['MAIL_PORT'],'timeout':10}
    if cfg.get('MAIL_SSL'):kwargs['context']=ssl.create_default_context()
    with cls(**kwargs) as mail:
        if not cfg.get('MAIL_SSL'):
            mail.starttls(context=ssl.create_default_context())
        if cfg.get('MAIL_USERNAME'):mail.login(cfg['MAIL_USERNAME'],cfg['MAIL_PASSWORD'])
        mail.send_message(msg)


def begin(user):
    address=user.get('email') or ''
    if '@' not in address:raise RuntimeError('A registered email address is required. Contact your administrator.')
    rate_limit('otp-send-account:'+str(user['user_id']),5,900)
    now=time.time()
    token=secrets.token_urlsafe(32);code=f'{secrets.randbelow(1000000):06d}'
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT MAX(created) AS last FROM email_challenges WHERE user_id=?',(user['user_id'],)).fetchone()
        if row['last'] and now-row['last']<60:raise RuntimeError('Please wait 60 seconds before requesting another code.')
        db.execute('DELETE FROM email_challenges WHERE user_id=? OR expires<?',(user['user_id'],now))
        db.execute('INSERT INTO email_challenges VALUES(?,?,?,?,?,0,?)',(token,user['user_id'],digest(token,code),credential_fingerprint(user['password_hash']+'|'+address),now+300,now))
    try:send_code(address,code)
    except Exception:
        with connect() as db:db.execute('DELETE FROM email_challenges WHERE token=?',(token,))
        raise
    session.clear();session['otp_token']=token;session['otp_role']=user['role']
    local,domain=address.split('@',1);session['otp_address']=local[:1]+'***@'+domain


def pending():
    with connect() as db:
        row=db.execute('SELECT * FROM email_challenges WHERE token=?',(session.get('otp_token',''),)).fetchone()
        return dict(row) if row else None


def consume(code,user):
    rate_limit('otp-verify-account:'+str(user['user_id']),15,900)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM email_challenges WHERE token=?',(session.get('otp_token',''),)).fetchone()
        if not row or row['expires']<=time.time() or row['attempts']>=5:return False
        db.execute('UPDATE email_challenges SET attempts=attempts+1 WHERE token=?',(row['token'],))
        valid=(row['user_id']==user['user_id'] and user['status']=='ACTIVE'
            and hmac.compare_digest(row['credential'],credential_fingerprint(user['password_hash']+'|'+(user.get('email') or '')))
            and hmac.compare_digest(row['digest'],digest(row['token'],code)))
        if valid:db.execute('DELETE FROM email_challenges WHERE token=?',(row['token'],))
        return valid
