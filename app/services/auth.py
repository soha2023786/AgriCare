"""Small self-hosted bearer-token auth for farmer-owned financial records."""
import os, sqlite3, hashlib, secrets, hmac, json, base64, time
from pathlib import Path
from .analytics import DB_PATH, _connect, init_db

def _secret(): return os.getenv('AGRICARE_AUTH_SECRET','')

def _b64(b): return base64.urlsafe_b64encode(b).decode().rstrip('=')
def _unb64(s): return base64.urlsafe_b64decode(s+'='*((4-len(s)%4)%4))

def init_auth():
    init_db()
    with _connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS farmer_accounts(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,created_at TEXT NOT NULL)''')

def _hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),240000).hex()

def register(name,email=None,password=None):
    # Backward-compatible service call: register(email, password).
    if password is None:
        password=email; email=name; name=str(email).split('@')[0]
    init_auth(); name=name.strip(); email=email.strip().lower()
    if not name: raise ValueError("Enter your name.")
    if len(password)<10: raise ValueError('Password must contain at least 10 characters.')
    salt=secrets.token_hex(16); uid=secrets.token_urlsafe(18)
    from datetime import datetime,timezone
    try:
        with _connect() as db:db.execute('INSERT INTO farmer_accounts(id,name,email,password_hash,salt,created_at) VALUES(?,?,?,?,?,?)',(uid,name,email,_hash(password,salt),salt,datetime.now(timezone.utc).isoformat()))
    except Exception as exc:
        if isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ == 'UniqueViolation': raise ValueError('An account with this email already exists.')
        raise
    return {'farmer_id':uid,'name':name,'email':email}

def login(email,password):
    init_auth(); email=email.strip().lower()
    with _connect() as db:r=db.execute('SELECT * FROM farmer_accounts WHERE email=?',(email,)).fetchone()
    if not r or not hmac.compare_digest(r['password_hash'],_hash(password,r['salt'])):return None
    return {'farmer_id':r['id'],'name':r['name'],'email':r['email']}

def issue_token(user):
    secret=_secret()
    if not secret: raise RuntimeError('Set AGRICARE_AUTH_SECRET in the environment before issuing farmer tokens.')
    header=_b64(json.dumps({'alg':'HS256','typ':'JWT'},separators=(',',':')).encode())
    payload=_b64(json.dumps({'sub':user['farmer_id'],'email':user['email'],'name':user.get('name',''),'exp':int(time.time())+43200},separators=(',',':')).encode())
    body=header+'.'+payload; sig=_b64(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
    return body+'.'+sig

def verify_token(token):
    secret=_secret()
    if not secret:return None
    try:
        h,p,s=token.split('.'); body=h+'.'+p
        expected=_b64(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(s,expected):return None
        payload=json.loads(_unb64(p))
        if int(payload.get('exp',0))<int(time.time()):return None
        return {'farmer_id':payload['sub'],'email':payload.get('email'),'name':payload.get('name','')}
    except Exception:return None
