import base64
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

from fastapi import HTTPException
import pyotp
import pytest

from test_api import environment, sign_in
from app import auth
from app.authenticator import allow_initial_setup, issue_initial_activation
from app.db import connect


def prepare(client, creds):
    activation = issue_initial_activation(creds['username'])
    proof = {'username':creds['username'], 'password':creds['password'], 'kind':'activation', 'proof':activation}
    response = client.post('/api/auth/authenticator/start', json=proof)
    assert response.status_code == 200, response.text
    return response.json(), proof


def enroll(client, creds):
    pending, proof = prepare(client, creds)
    response = client.post('/api/auth/authenticator/confirm', json={'token':pending['token'], 'code':pyotp.TOTP(pending['setup_key']).now()})
    assert response.status_code == 200, response.text
    return response.json(), pending, proof


def test_initial_pairing_requires_password_and_activation_and_grants_no_session(environment):
    client, creds = environment
    initial = issue_initial_activation('tester')
    body = {'username':'tester', 'password':creds['password'], 'kind':'activation', 'proof':initial}
    assert client.post('/api/auth/authenticator/start', json={**body,'password':'incorrect'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json={**body,'proof':'000000'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json={**body,'username':'missing'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json=body, headers={'Origin':'https://evil.example'}).status_code == 403
    response = client.post('/api/auth/authenticator/start', json=body)
    assert response.status_code == 200 and response.headers['cache-control']=='no-store'
    pending = response.json()
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/session').json()['authenticated'] is False
    svg = ElementTree.fromstring(base64.b64decode(pending['qr_image'].split(',')[1]))
    assert svg.tag.endswith('svg') and svg.find('{http://www.w3.org/2000/svg}path') is not None
    with connect() as conn:
        row = conn.execute('SELECT * FROM mfa_enrollments').fetchone()
        assert row['token_hash']==auth.digest(pending['token'])
        assert row['secret_encrypted'] != pending['setup_key']
        assert conn.execute('SELECT 1 FROM mfa_activation_grants').fetchone() is None
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401
    # Password-only sign-in does not bypass the second factor.
    assert client.post('/api/auth/login', json={'username':'tester','password':creds['password']}).status_code==422


def test_confirm_rotates_secret_invalidates_sessions_and_returns_codes_once(environment):
    client, creds = environment
    sign_in(client, creds)
    old_cookie = client.cookies.get(auth.COOKIE)
    result, pending, proof = enroll(client, creds)
    assert result['authenticated'] and len(result['recovery_codes'])==10
    assert len(set(result['recovery_codes']))==10
    assert client.cookies.get(auth.COOKIE)!=old_cookie
    assert client.get('/api/account').json()['authenticator_enrolled'] is True
    assert client.get('/api/account').json()['recovery_codes_remaining']==10
    body = {'token':pending['token'], 'code':pyotp.TOTP(pending['setup_key']).now()}
    assert client.post('/api/auth/authenticator/confirm', json=body).status_code==400
    assert client.post('/api/auth/login', json=creds).status_code==401
    assert client.post('/api/auth/login', json={**creds,'totp':body['code']}).status_code==401
    with connect() as conn:
        assert conn.execute('SELECT 1 FROM staff_sessions WHERE token_hash=%s',(auth.digest(old_cookie),)).fetchone() is None
        assert conn.execute('SELECT 1 FROM mfa_enrollments').fetchone() is None
        hashes = {r['code_hash'] for r in conn.execute('SELECT code_hash FROM mfa_recovery_codes')}
        assert {auth.digest(auth.normalize_code(c)) for c in result['recovery_codes']}==hashes
        # Audit details must never contain secrets/codes.
        logs = str(conn.execute('SELECT * FROM audit_events').fetchall())
        assert pending['setup_key'] not in logs and pending['token'] not in logs
        assert all(code not in logs for code in result['recovery_codes'])
        conn.execute('UPDATE staff_accounts SET last_totp_step=-1')
    assert client.post('/api/auth/login', json={**creds,'totp':pyotp.TOTP(pending['setup_key']).now()}).status_code==200
    with pytest.raises(ValueError): issue_initial_activation('tester')
    assert client.post('/api/auth/authenticator/start', json=proof).status_code==401


def test_confirmation_attempt_limit_expiry_cancel_and_account_changes(environment):
    client, creds = environment
    pending, _ = prepare(client, creds)
    correct = pyotp.TOTP(pending['setup_key']).now()
    bad = '111111' if correct!='111111' else '222222'
    for _ in range(5):
        assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'],'code':bad}).status_code==401
    assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'],'code':correct}).status_code==400
    pending, _ = prepare(client, creds)
    with connect() as conn: conn.execute("UPDATE mfa_enrollments SET expires_at=now()-interval '1 second'")
    assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'],'code':pyotp.TOTP(pending['setup_key']).now()}).status_code==400
    pending, _ = prepare(client, creds)
    assert client.post('/api/auth/authenticator/cancel', json={'token':pending['token']}).status_code==200
    assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'],'code':pyotp.TOTP(pending['setup_key']).now()}).status_code==400
    pending, _ = prepare(client, creds)
    with connect() as conn: conn.execute("UPDATE staff_accounts SET password_hash=%s", (auth.PASSWORDS.hash('changed-password'),))
    assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'],'code':pyotp.TOTP(pending['setup_key']).now()}).status_code==400


def test_recovery_code_single_use_password_required_and_concurrent_consumption(environment):
    client, creds = environment
    result, _, _ = enroll(client, creds)
    code = result['recovery_codes'][0]
    body = {'username':'tester','password':creds['password'],'recovery_code':code}
    assert client.post('/api/auth/login', json={**body,'password':'wrong'}).status_code==401
    with ThreadPoolExecutor(max_workers=2) as executor:
        def attempt(_):
            try:
                auth.authenticate('tester',creds['password'],recovery_code=code)
                return 200
            except HTTPException as error: return error.status_code
        assert sorted(executor.map(attempt, range(2))) == [200,401]
    assert client.post('/api/auth/login', json=body).status_code==401
    assert client.post('/api/auth/login', json={**body,'recovery_code':result['recovery_codes'][1]}).status_code==200
    assert client.get('/api/account').json()['recovery_codes_remaining']==8


def test_recovery_can_replace_lost_authenticator_and_old_codes_revoked(environment):
    client, creds = environment
    original, first, _ = enroll(client, creds)
    proof = {'username':'tester','password':creds['password'],'kind':'recovery','proof':original['recovery_codes'][0]}
    response = client.post('/api/auth/authenticator/start',json=proof)
    assert response.status_code==200
    pending = response.json()
    assert pending['setup_key'] != first['setup_key']
    response = client.post('/api/auth/authenticator/confirm',json={'token':pending['token'],'code':pyotp.TOTP(pending['setup_key']).now()})
    assert response.status_code==200
    assert client.post('/api/auth/login',json={'username':'tester','password':creds['password'],'recovery_code':original['recovery_codes'][1]}).status_code==401
    assert client.post('/api/auth/login',json={**creds,'totp':pyotp.TOTP(first['setup_key']).now()}).status_code==401


def test_recovery_regeneration_requires_session_csrf_and_current_totp(environment):
    client, creds = environment
    result, pending, _ = enroll(client, creds)
    with connect() as conn: conn.execute('UPDATE staff_accounts SET last_totp_step=-1')
    body = {'username':'tester','password':creds['password'],'kind':'totp','proof':pyotp.TOTP(pending['setup_key']).now()}
    assert client.post('/api/auth/authenticator/recovery-codes',json=body).status_code==403
    headers = {'X-CSRF-Token':result['csrf_token']}
    assert client.post('/api/auth/authenticator/recovery-codes',headers=headers,json={**body,'username':'other'}).status_code==400
    assert client.post('/api/auth/authenticator/recovery-codes',headers=headers,json={**body,'kind':'activation'}).status_code==400
    response = client.post('/api/auth/authenticator/recovery-codes',headers=headers,json=body)
    assert response.status_code==200 and len(response.json()['recovery_codes'])==10
    assert client.post('/api/auth/login',json={'username':'tester','password':creds['password'],'recovery_code':result['recovery_codes'][0]}).status_code==401


def test_activation_expiry_disabled_account_and_failure_throttle(environment):
    client, creds = environment
    code = issue_initial_activation('tester')
    body = {'username':'tester','password':creds['password'],'kind':'activation','proof':code}
    with connect() as conn: conn.execute("UPDATE mfa_activation_grants SET expires_at=now()-interval '1 second'")
    assert client.post('/api/auth/authenticator/start',json=body).status_code==401
    code=issue_initial_activation('tester'); body['proof']=code
    with connect() as conn: conn.execute('UPDATE staff_accounts SET active=false')
    assert client.post('/api/auth/authenticator/start',json=body).status_code==401
    with connect() as conn: conn.execute('UPDATE staff_accounts SET active=true')
    for _ in range(6):
        assert client.post('/api/auth/authenticator/start',json={**body,'password':'wrong'}).status_code==401
    assert client.post('/api/auth/authenticator/start',json=body).status_code==429


def test_simple_initial_setup_is_explicit_password_protected_and_has_no_data_access(environment):
    client, creds = environment
    body = {'username':'tester', 'password':creds['password'], 'kind':'initial'}
    # Legacy unpaired accounts are not automatically authorized for simpler setup.
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401
    allow_initial_setup('tester')
    assert client.post('/api/auth/authenticator/start', json={**body, 'password':'wrong'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json={**body, 'username':'missing'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json=body, headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/auth/authenticator/start', json={**body, 'kind':'totp'}).status_code == 422
    response = client.post('/api/auth/authenticator/start', json=body)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert 'set-cookie' not in response.headers
    pending = response.json()
    for path in ['/api/dashboard', '/api/imports', '/api/audit', '/api/account']:
        assert client.get(path).status_code == 401
    assert client.get('/api/session').json() == {'authenticated':False}
    with connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM staff_sessions').fetchone()['n'] == 0
        row = conn.execute('SELECT * FROM mfa_enrollments').fetchone()
        assert row['initial_setup'] and row['secret_encrypted'] != pending['setup_key']
        logs = str(conn.execute('SELECT * FROM audit_events').fetchall())
        assert pending['token'] not in logs and pending['setup_key'] not in logs
    result = client.post('/api/auth/authenticator/confirm', json={'token':pending['token'], 'code':pyotp.TOTP(pending['setup_key']).now()})
    assert result.status_code == 200 and len(result.json()['recovery_codes']) == 10
    assert client.get('/api/dashboard').status_code == 200
    with connect() as conn:
        assert conn.execute('SELECT 1 FROM mfa_initial_permissions').fetchone() is None
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401
    with pytest.raises(ValueError): allow_initial_setup('tester')
    # Even a mistakenly inserted permission cannot turn first setup into an MFA reset.
    with connect() as conn:
        from app.authenticator import binding
        account = conn.execute('SELECT * FROM staff_accounts').fetchone()
        conn.execute("INSERT INTO mfa_initial_permissions(staff_id,account_binding,expires_at) VALUES(%s,%s,now()+interval '1 hour')", (account['id'],binding(account)))
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401


def test_initial_setup_restart_expiry_revocation_binding_and_disabled_account(environment):
    client, creds = environment
    body = {'username':'tester', 'password':creds['password'], 'kind':'initial'}
    allow_initial_setup('tester')
    first = client.post('/api/auth/authenticator/start', json=body).json()
    second = client.post('/api/auth/authenticator/start', json=body).json()
    assert first['token'] != second['token'] and first['setup_key'] != second['setup_key']
    assert client.post('/api/auth/authenticator/confirm', json={'token':first['token'], 'code':pyotp.TOTP(first['setup_key']).now()}).status_code == 400
    assert client.post('/api/auth/authenticator/cancel', json={'token':second['token']}).status_code == 200
    third = client.post('/api/auth/authenticator/start', json=body).json()
    with connect() as conn:
        conn.execute("UPDATE mfa_initial_permissions SET expires_at=now()-interval '1 second'")
    assert client.post('/api/auth/authenticator/confirm', json={'token':third['token'], 'code':pyotp.TOTP(third['setup_key']).now()}).status_code == 400
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401
    allow_initial_setup('tester')
    with connect() as conn:
        conn.execute("UPDATE mfa_initial_permissions SET expires_at=now()+interval '2 minutes'")
    pending = client.post('/api/auth/authenticator/start', json=body).json()
    with connect() as conn:
        row = conn.execute('SELECT e.expires_at AS qr_expiry,p.expires_at AS permission_expiry FROM mfa_enrollments e JOIN mfa_initial_permissions p USING(staff_id)').fetchone()
        assert row['qr_expiry'] == row['permission_expiry']
        conn.execute('DELETE FROM mfa_initial_permissions')
    assert client.post('/api/auth/authenticator/confirm', json={'token':pending['token'], 'code':pyotp.TOTP(pending['setup_key']).now()}).status_code == 400
    allow_initial_setup('tester')
    with connect() as conn: conn.execute('UPDATE staff_accounts SET active=false')
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 401
    with connect() as conn:
        conn.execute('UPDATE staff_accounts SET active=true,password_hash=%s', (auth.PASSWORDS.hash('a-new-password'),))
    assert client.post('/api/auth/authenticator/start', json={**body,'password':'a-new-password'}).status_code == 401


def test_simple_setup_throttles_and_only_one_concurrent_confirmation_succeeds(environment):
    client, creds = environment
    allow_initial_setup('tester')
    body = {'username':'tester', 'password':creds['password'], 'kind':'initial'}
    pending = client.post('/api/auth/authenticator/start', json=body).json()
    code = pyotp.TOTP(pending['setup_key']).now()
    from app.authenticator import Confirmation, confirm
    def attempt(_):
        try:
            confirm(Confirmation(token=pending['token'], code=code))
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == [200,400]
    with connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM staff_sessions').fetchone()['n'] == 1
    for _ in range(8):
        assert client.post('/api/auth/authenticator/start', json={**body,'password':'wrong'}).status_code == 401
    assert client.post('/api/auth/authenticator/start', json=body).status_code == 429


def test_password_first_routes_to_qr_then_requires_mfa_on_later_login(environment):
    client, creds = environment
    allow_initial_setup('tester')
    password = {'username':'tester', 'password':creds['password']}
    response = client.post('/api/auth/authenticator/next', json=password)
    assert response.status_code == 200 and response.json()['step'] == 'setup'
    assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
    pending = response.json()
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/session').json() == {'authenticated':False}
    result = client.post('/api/auth/authenticator/confirm', json={'token':pending['token'], 'code':pyotp.TOTP(pending['setup_key']).now()})
    assert result.status_code == 200 and result.json()['authenticated']
    client.post('/api/auth/logout', headers={'X-CSRF-Token':result.json()['csrf_token']})
    response = client.post('/api/auth/authenticator/next', json=password)
    assert response.status_code == 200 and response.json() == {'step':'code', 'username':'tester'}
    assert 'set-cookie' not in response.headers and client.get('/api/dashboard').status_code == 401
    assert client.post('/api/auth/login', json=password).status_code == 422
    assert client.post('/api/auth/login', json={**password,'totp':pyotp.TOTP(pending['setup_key']).now()}).status_code == 401
    # A fresh factor is still required; recovery login also completes the second step.
    assert client.post('/api/auth/login', json={**password,'recovery_code':result.json()['recovery_codes'][0]}).status_code == 200


def test_password_first_does_not_grant_setup_to_arbitrary_unpaired_or_expired_accounts(environment):
    client, creds = environment
    body = {'username':'tester', 'password':creds['password']}
    for update in [None, 'expired', 'changed_binding']:
        if update:
            allow_initial_setup('tester')
            with connect() as conn:
                if update == 'expired': conn.execute("UPDATE mfa_initial_permissions SET expires_at=now()-interval '1 second'")
                else: conn.execute("UPDATE mfa_initial_permissions SET account_binding='invalid'")
        response = client.post('/api/auth/authenticator/next', json=body)
        assert response.status_code == 200 and response.json() == {'step':'code','username':'tester'}
        with connect() as conn:
            assert conn.execute('SELECT 1 FROM mfa_enrollments').fetchone() is None
            assert conn.execute('SELECT 1 FROM staff_sessions').fetchone() is None


def test_password_first_rejects_wrong_credentials_disabled_accounts_origins_and_throttles(environment):
    client, creds = environment
    allow_initial_setup('tester')
    body = {'username':'tester', 'password':creds['password']}
    assert client.post('/api/auth/authenticator/next', json=body, headers={'Origin':'https://evil.example'}).status_code == 403
    wrong = client.post('/api/auth/authenticator/next', json={**body,'password':'wrong'})
    missing = client.post('/api/auth/authenticator/next', json={**body,'username':'missing'})
    with connect() as conn: conn.execute('UPDATE staff_accounts SET active=false')
    disabled = client.post('/api/auth/authenticator/next', json=body)
    assert wrong.status_code == missing.status_code == disabled.status_code == 401
    assert wrong.json() == missing.json() == disabled.json()
    with connect() as conn:
        conn.execute('UPDATE staff_accounts SET active=true')
        assert conn.execute('SELECT 1 FROM mfa_enrollments').fetchone() is None
    for _ in range(5):
        assert client.post('/api/auth/authenticator/next', json={**body,'password':'wrong'}).status_code == 401
    assert client.post('/api/auth/authenticator/next', json=body).status_code == 429
