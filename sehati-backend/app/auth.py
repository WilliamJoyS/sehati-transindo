"""Bounded local authentication using Argon2 and PyOTP, not a production IdP.

Phone enrollment and recovery codes are implemented. Operator recovery, staff
lifecycle and production security review remain deployment work. This module
refuses remote traffic via the app middleware.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import time

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
import pyotp
from fastapi.responses import JSONResponse

from .db import LOCAL, connect
from .settings import PRODUCTION, ENCRYPTION_KEY_FILE

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
COOKIE = "__Host-sehati_session" if PRODUCTION else "sehati_local_session"


def cipher():
    if PRODUCTION:
        return Fernet(ENCRYPTION_KEY_FILE.read_text(encoding="utf-8").strip().encode())
    config = json.loads((LOCAL / "app-secrets.json").read_text(encoding="utf-8"))
    return Fernet(config["encryption_key"].encode())


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session(request: Request, required=True):
    token = request.cookies.get(COOKIE, "")
    row = None
    if 20 <= len(token) <= 200:
        with connect() as conn:
            row = conn.execute(
                """SELECT a.id,a.username,a.role,s.csrf_token,s.token_hash
                FROM staff_sessions s JOIN staff_accounts a ON a.id=s.staff_id
                WHERE s.token_hash=%s AND a.active AND s.expires_at>now()
                AND s.last_seen>now()-interval '30 minutes'""", (digest(token),)
            ).fetchone()
            if row:
                conn.execute("UPDATE staff_sessions SET last_seen=now() WHERE token_hash=%s", (row["token_hash"],))
    if required and not row:
        raise HTTPException(401, "Silakan masuk dengan akun staf dan kode autentikator.")
    return row


def require_write(request, roles=("admin", "importer")):
    user = session(request)
    if user["role"] not in roles:
        raise HTTPException(403, "Akun ini tidak memiliki izin untuk tindakan tersebut.")
    submitted = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(submitted, user["csrf_token"]):
        raise HTTPException(403, "Token keamanan tidak valid. Muat ulang halaman.")
    return user


def public_session(user):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": {"username": user["username"], "role": user["role"]}, "csrf_token": user["csrf_token"]}


def normalize_code(value):
    return value.strip().replace('-', '').replace(' ', '').upper()


def lock_auth(conn):
    conn.execute("SELECT pg_advisory_xact_lock(813024)")


def check_attempts(conn):
    recent = conn.execute("SELECT count(*) AS n FROM login_attempts WHERE NOT successful AND created_at>now()-interval '5 minutes'").fetchone()['n']
    if recent >= 8:
        raise HTTPException(429, 'Terlalu banyak percobaan. Tunggu lima menit.')


def valid_totp(secret, code, last_step=-1):
    step = int(time.time()) // 30
    verifier = pyotp.TOTP(secret)
    for candidate in (step, step - 1, step + 1):
        if candidate > last_step and secrets.compare_digest(verifier.at(candidate * 30), code):
            return candidate
    return None


def record_attempt(conn, username, ok, action='login_failed'):
    conn.execute('INSERT INTO login_attempts(username,successful) VALUES(%s,%s)', (username, ok))
    if not ok:
        conn.execute('INSERT INTO audit_events(action) VALUES(%s)', (action,))
        conn.commit()
        raise HTTPException(401, 'Nama pengguna, kata sandi, atau kode tidak valid. Gunakan kode baru bila kode sebelumnya sudah dipakai.')


def verify_account(conn, username, password, kind, proof):
    """Password plus a consumed second factor; caller holds the authentication lock."""
    check_attempts(conn)
    username = username.strip().lower()
    account = conn.execute('SELECT * FROM staff_accounts WHERE username=%s FOR UPDATE', (username,)).fetchone()
    password_ok = PASSWORDS.verify(password, account['password_hash'] if account else DUMMY_HASH)
    ok = False
    if account and account['active'] and password_ok:
        if kind == 'totp':
            secret = cipher().decrypt(account['totp_encrypted'].encode()).decode()
            accepted = valid_totp(secret, proof, account['last_totp_step'])
            if accepted is not None:
                conn.execute('UPDATE staff_accounts SET last_totp_step=%s WHERE id=%s', (accepted, account['id']))
                ok = True
        elif kind == 'recovery':
            used = conn.execute('UPDATE mfa_recovery_codes SET used_at=now() WHERE staff_id=%s AND code_hash=%s AND used_at IS NULL RETURNING code_hash',
                                (account['id'], digest(normalize_code(proof)))).fetchone()
            ok = used is not None
            if ok:
                conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_recovery_used')", (account['id'],))
        elif kind == 'activation' and account['authenticator_enrolled_at'] is None:
            used = conn.execute('DELETE FROM mfa_activation_grants WHERE staff_id=%s AND code_hash=%s AND expires_at>now() RETURNING staff_id',
                                (account['id'], digest(normalize_code(proof)))).fetchone()
            ok = used is not None
    record_attempt(conn, username, ok)
    return account


def create_session(conn, account):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    conn.execute('DELETE FROM staff_sessions WHERE expires_at<=now()')
    conn.execute('INSERT INTO staff_sessions(token_hash,staff_id,csrf_token,expires_at) VALUES(%s,%s,%s,%s)',
                 (digest(token), account['id'], csrf, datetime.now(timezone.utc) + timedelta(hours=8)))
    conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'login_succeeded')", (account['id'],))
    return token, {'username': account['username'], 'role': account['role'], 'csrf_token': csrf}


def session_response(token, user, extra=None):
    response = JSONResponse({**public_session(user), **(extra or {})})
    # This application still accepts loopback HTTP only. Production requires HTTPS/Secure.
    response.set_cookie(COOKIE, token, max_age=8 * 3600, httponly=True, samesite='strict', secure=PRODUCTION, path='/')
    return response


def authenticate(username, password, totp_code=None, recovery_code=None):
    """Fail closed, throttle all local attempts, and reject reused TOTP steps."""
    with connect() as conn:
        lock_auth(conn)
        account = verify_account(conn, username, password, 'recovery' if recovery_code else 'totp', recovery_code or totp_code or '')
        if recovery_code:
            conn.execute('DELETE FROM staff_sessions WHERE staff_id=%s', (account['id'],))
            conn.execute('DELETE FROM mfa_enrollments WHERE staff_id=%s', (account['id'],))
        return create_session(conn, account)
