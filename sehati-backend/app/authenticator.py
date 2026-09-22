"""Self-service authenticator enrollment, with no email or third-party QR service."""
import base64
from datetime import datetime, timedelta, timezone
import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
import pyotp
import qrcode
from qrcode.image.svg import SvgPathFillImage

from . import auth
from .db import connect

router = APIRouter(prefix='/api/auth/authenticator', tags=['Staff authenticator'])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class Proof(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    kind: Literal['totp', 'recovery', 'activation']
    proof: str = Field(min_length=6, max_length=128)


class StartProof(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    kind: Literal['initial', 'totp', 'recovery', 'activation']
    proof: str | None = Field(default=None, min_length=6, max_length=128)

    @model_validator(mode='after')
    def require_existing_factor(self):
        if self.kind != 'initial' and not self.proof:
            raise ValueError('Kode aplikasi atau kode pemulihan diperlukan untuk mengganti authenticator.')
        if self.kind == 'initial' and self.proof is not None:
            raise ValueError('Pemasangan pertama tidak menggunakan kode aktivasi.')
        return self


class Pending(BaseModel):
    token: str = Field(min_length=40, max_length=128)


class Confirmation(Pending):
    code: str = Field(pattern=r'^[0-9]{6}$')


def binding(account):
    return auth.digest(account['password_hash'] + ':' + account['totp_encrypted'])


def allow_initial_setup(username):
    """Operator-only opt-in for a known, unpaired account; never an MFA reset.

    Initial enrollment trusts the existing password for 24 hours. Operators must
    verify the account owner before explicitly enabling this permission.
    """
    with connect() as conn:
        auth.lock_auth(conn)
        account = conn.execute('SELECT * FROM staff_accounts WHERE username=%s AND active FOR UPDATE', (username,)).fetchone()
        if not account or account['authenticator_enrolled_at'] is not None:
            raise ValueError('Akun tidak tersedia untuk pemasangan pertama. Gunakan aplikasi atau kode pemulihan yang sudah dimiliki.')
        row = conn.execute('''INSERT INTO mfa_initial_permissions(staff_id,account_binding,expires_at)
            VALUES(%s,%s,now()+interval '24 hours') ON CONFLICT(staff_id) DO UPDATE
            SET account_binding=excluded.account_binding,expires_at=excluded.expires_at,created_at=now()
            RETURNING expires_at''', (account['id'], binding(account))).fetchone()
        conn.execute('DELETE FROM mfa_enrollments WHERE staff_id=%s', (account['id'],))
        conn.execute('DELETE FROM mfa_activation_grants WHERE staff_id=%s', (account['id'],))
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_initial_setup_allowed')", (account['id'],))
        return row['expires_at']


def initial_permission(conn, account):
    if account['authenticator_enrolled_at'] is not None:
        return None
    permission = conn.execute('SELECT * FROM mfa_initial_permissions WHERE staff_id=%s AND expires_at>now()', (account['id'],)).fetchone()
    if permission and secrets.compare_digest(permission['account_binding'], binding(account)):
        return permission
    return None


def verify_initial_account(conn, username, password):
    # A password can start only this explicitly allowed setup, never a staff session.
    auth.check_attempts(conn)
    username = username.strip().lower()
    account = conn.execute('SELECT * FROM staff_accounts WHERE username=%s FOR UPDATE', (username,)).fetchone()
    password_ok = auth.PASSWORDS.verify(password, account['password_hash'] if account else auth.DUMMY_HASH)
    permission = initial_permission(conn, account) if account and account['active'] and password_ok else None
    auth.record_attempt(conn, username, permission is not None, 'mfa_initial_setup_failed')
    return account, permission


def replace_recovery_codes(conn, staff_id):
    # 128 random bits per code; only hashes are stored. Displayed once on success.
    codes = []
    for _ in range(10):
        raw = secrets.token_hex(16).upper()
        codes.append('-'.join(raw[i:i+4] for i in range(0, len(raw), 4)))
    conn.execute('DELETE FROM mfa_recovery_codes WHERE staff_id=%s', (staff_id,))
    for code in codes:
        conn.execute('INSERT INTO mfa_recovery_codes(staff_id,code_hash) VALUES(%s,%s)', (staff_id, auth.digest(auth.normalize_code(code))))
    return codes


def issue_initial_activation(username):
    """Operator-only provisioning. Never usable to reset an enrolled authenticator."""
    raw = secrets.token_hex(24).upper()
    code = '-'.join(raw[i:i+8] for i in range(0, len(raw), 8))
    with connect() as conn:
        auth.lock_auth(conn)
        account = conn.execute('SELECT * FROM staff_accounts WHERE username=%s AND active FOR UPDATE', (username,)).fetchone()
        if not account or account['authenticator_enrolled_at'] is not None:
            raise ValueError('Akun tidak tersedia untuk aktivasi awal. Gunakan autentikator atau kode pemulihan yang sudah dimiliki.')
        conn.execute('''INSERT INTO mfa_activation_grants(staff_id,code_hash,expires_at) VALUES(%s,%s,now()+interval '24 hours')
            ON CONFLICT(staff_id) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,created_at=now()''',
            (account['id'], auth.digest(auth.normalize_code(code))))
        conn.execute('DELETE FROM mfa_enrollments WHERE staff_id=%s', (account['id'],))
        conn.execute('DELETE FROM mfa_initial_permissions WHERE staff_id=%s', (account['id'],))
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_initial_activation_issued')", (account['id'],))
    return code


def create_enrollment(conn, account, permission=None):
    secret, token = pyotp.random_base32(), secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    if permission:
        expires = min(expires, permission['expires_at'])
    conn.execute('DELETE FROM mfa_enrollments WHERE staff_id=%s OR expires_at<=now()', (account['id'],))
    conn.execute('''INSERT INTO mfa_enrollments(token_hash,staff_id,secret_encrypted,account_binding,expires_at,initial_setup)
        VALUES(%s,%s,%s,%s,%s,%s)''', (auth.digest(token), account['id'], auth.cipher().encrypt(secret.encode()).decode(), binding(account), expires, permission is not None))
    conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_enrollment_started')", (account['id'],))
    uri = pyotp.TOTP(secret).provisioning_uri(name=account['username'], issuer_name='Sehati')
    svg = qrcode.make(uri, image_factory=SvgPathFillImage, border=4).to_string()
    return {'token': token, 'username': account['username'], 'expires_at': expires.isoformat(),
            'qr_image': 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode(), 'setup_key': secret}


@router.post('/next')
def next_step(data: Credentials):
    """Password-first routing, never a login or authorization to reset MFA.

    Existing accounts still submit password + second factor to /api/auth/login.
    Only an explicit, current initial permission permits returning a setup QR.
    """
    with connect() as conn:
        auth.lock_auth(conn)
        auth.check_attempts(conn)
        username = data.username.strip().lower()
        account = conn.execute('SELECT * FROM staff_accounts WHERE username=%s FOR UPDATE', (username,)).fetchone()
        password_ok = auth.PASSWORDS.verify(data.password, account['password_hash'] if account else auth.DUMMY_HASH)
        auth.record_attempt(conn, username, bool(account and account['active'] and password_ok))
        permission = initial_permission(conn, account)
        if permission:
            return {'step': 'setup', **create_enrollment(conn, account, permission)}
        # Includes legacy accounts: having no phone pairing is not permission to reset.
        return {'step': 'code', 'username': account['username']}


@router.post('/start')
def start(data: StartProof):
    with connect() as conn:
        auth.lock_auth(conn)
        permission = None
        if data.kind == 'initial':
            account, permission = verify_initial_account(conn, data.username, data.password)
        else:
            account = auth.verify_account(conn, data.username, data.password, data.kind, data.proof)
        return create_enrollment(conn, account, permission)


@router.post('/confirm')
def confirm(data: Confirmation):
    with connect() as conn:
        auth.lock_auth(conn)
        auth.check_attempts(conn)
        pending = conn.execute('SELECT * FROM mfa_enrollments WHERE token_hash=%s FOR UPDATE', (auth.digest(data.token),)).fetchone()
        if not pending or pending['expires_at'] <= datetime.now(timezone.utc) or pending['attempts'] >= 5:
            raise HTTPException(400, 'QR sudah kedaluwarsa atau tidak valid. Kembali dan mulai pemasangan lagi.')
        account = conn.execute('SELECT * FROM staff_accounts WHERE id=%s FOR UPDATE', (pending['staff_id'],)).fetchone()
        if not account or not account['active'] or not secrets.compare_digest(binding(account), pending['account_binding']):
            raise HTTPException(400, 'Akses akun berubah. Mulai pemasangan kembali.')
        if pending['initial_setup'] and not initial_permission(conn, account):
            raise HTTPException(400, 'Izin pemasangan pertama telah berakhir. Hubungi pengelola akun.')
        secret = auth.cipher().decrypt(pending['secret_encrypted'].encode()).decode()
        step = auth.valid_totp(secret, data.code)
        if step is None:
            conn.execute('UPDATE mfa_enrollments SET attempts=attempts+1 WHERE token_hash=%s', (pending['token_hash'],))
            auth.record_attempt(conn, account['username'], False, 'mfa_confirmation_failed')
        conn.execute('UPDATE staff_accounts SET totp_encrypted=%s,last_totp_step=%s,authenticator_enrolled_at=now() WHERE id=%s',
                     (pending['secret_encrypted'], step, account['id']))
        conn.execute('DELETE FROM staff_sessions WHERE staff_id=%s', (account['id'],))
        conn.execute('DELETE FROM mfa_activation_grants WHERE staff_id=%s', (account['id'],))
        conn.execute('DELETE FROM mfa_initial_permissions WHERE staff_id=%s', (account['id'],))
        conn.execute('DELETE FROM mfa_enrollments WHERE staff_id=%s', (account['id'],))
        codes = replace_recovery_codes(conn, account['id'])
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_enrollment_completed')", (account['id'],))
        token, user = auth.create_session(conn, account)
    return auth.session_response(token, user, {'recovery_codes': codes})


@router.post('/cancel')
def cancel(data: Pending):
    with connect() as conn:
        conn.execute('DELETE FROM mfa_enrollments WHERE token_hash=%s', (auth.digest(data.token),))
    return {'cancelled': True}


@router.post('/recovery-codes')
def regenerate_codes(data: Proof, request: Request):
    user = auth.require_write(request, roles=('admin', 'importer', 'viewer'))
    if data.kind != 'totp' or data.username.strip().lower() != user['username']:
        raise HTTPException(400, 'Gunakan kata sandi dan kode autentikator baru untuk akun yang sedang masuk.')
    with connect() as conn:
        auth.lock_auth(conn)
        account = auth.verify_account(conn, data.username, data.password, 'totp', data.proof)
        codes = replace_recovery_codes(conn, account['id'])
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'mfa_recovery_codes_replaced')", (account['id'],))
    return {'recovery_codes': codes}
