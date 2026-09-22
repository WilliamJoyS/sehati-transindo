"""Integration checks against a newly-created, isolated PostgreSQL test database."""
import json
import secrets
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
import pyotp
import pytest

from app.db import LOCAL, connect
from app.main import app, MAX_UPLOAD


@pytest.fixture()
def environment(monkeypatch):
    runtime = json.loads((LOCAL / 'runtime.json').read_text(encoding='utf-8-sig'))
    database = 'sehati_test_' + uuid4().hex
    with psycopg.connect(runtime['admin_database_url'], autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {} OWNER sehati_app').format(sql.Identifier(database)))
    settings = conninfo_to_dict(runtime['database_url'])
    settings['dbname'] = database
    monkeypatch.setenv('SEHATI_DATABASE_URL', make_conninfo(**settings))
    password, secret = secrets.token_urlsafe(24), pyotp.random_base32()
    key = json.loads((LOCAL / 'app-secrets.json').read_text())['encryption_key']
    try:
        with TestClient(app, base_url='http://127.0.0.1:8000', client=('127.0.0.1', 51000), headers={'Origin': 'http://127.0.0.1:8000'}) as client:
            with connect() as conn:
                conn.execute("INSERT INTO staff_accounts(id,username,password_hash,totp_encrypted,role) VALUES(%s,'tester',%s,%s,'admin')", (uuid4(), PasswordHash.recommended().hash(password), Fernet(key.encode()).encrypt(secret.encode()).decode()))
            credentials = {'username': 'tester', 'password': password, 'totp': pyotp.TOTP(secret).now()}
            yield client, credentials
    finally:
        # Drop only this fixture's randomly named database, never the local app DB.
        assert database.startswith('sehati_test_') and len(database) == 44
        with psycopg.connect(runtime['admin_database_url'], autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))


def sign_in(client, credentials):
    response = client.post('/api/auth/login', json=credentials)
    assert response.status_code == 200, response.text
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=strict' in response.headers['set-cookie'].lower()
    return response.json()['csrf_token']


def test_public_site_health_private_paths_and_origin(environment):
    client, creds = environment
    assert client.get('/').status_code == 200
    assert client.get('/admin/').status_code == 200
    assert client.get('/api/health').json()['database'] == 'postgresql'
    assert client.get('/api/session').json() == {'authenticated': False}
    for url in ['/api/dashboard', '/api/imports', '/api/audit']:
        assert client.get(url).status_code == 401
    for url in ['/.local/runtime.json', '/admin/../.local/LOGIN.md', '/schema.sql', '/app/auth.py']:
        assert client.get(url).status_code == 404
    assert client.get('/api/health', headers={'Host': 'untrusted.example'}).status_code == 400
    assert client.post('/api/auth/login', json=creds, headers={'Origin': 'https://untrusted.example'}).status_code == 403
    assert client.get('/api/partner/v1/deliveries').status_code == 401


def test_login_mfa_replay_csrf_logout_and_revocation(environment):
    client, creds = environment
    assert client.post('/api/auth/login', json={**creds, 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={**creds, 'totp': '999999' if creds['totp'] != '999999' else '000000'}).status_code == 401
    csrf = sign_in(client, creds)
    assert client.get('/api/dashboard').status_code == 200
    assert client.post('/api/auth/login', json=creds).status_code == 401
    assert client.post('/api/auth/logout').status_code == 403
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 200
    assert client.get('/api/dashboard').status_code == 401


def test_preview_repeat_confirm_and_invalid_file(environment):
    client, creds = environment
    csrf = sign_in(client, creds)
    headers = {'X-CSRF-Token': csrf}
    customer = client.post('/api/customers', json={'code':'BRIDGE','name':'Bridgestone test'}, headers=headers)
    assert customer.status_code == 201
    customer_id = customer.json()['id']
    customer_form = {'customer_id':customer_id}
    sample = Path('C:/Users/PC/Downloads/BRIDGESTONE 2025.xlsx')
    if not sample.exists():
        pytest.skip('Private user workbook not present')
    payload = sample.read_bytes()
    request_file = {'file': ('BRIDGESTONE 2025.xlsx', payload, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    assert client.post('/api/imports/preview', files=request_file).status_code == 403
    response = client.post('/api/imports/preview', files=request_file, data=customer_form, headers=headers)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['summary']['do_rows'] == 826 and report['summary']['distinct_do'] == 819
    assert report['can_confirm'] is True
    assert client.get('/api/deliveries',params=customer_form).json()['total'] == 0
    committed = client.post(f"/api/imports/{report['batch_id']}/confirm", json={'expected_revision':report['revision']}, headers=headers)
    assert committed.status_code == 200 and committed.json()['status'] == 'committed'
    assert client.get('/api/deliveries',params=customer_form).json()['total'] == 826
    second = client.post('/api/imports/preview', files=request_file, data=customer_form, headers=headers).json()
    assert second['reused'] and second['batch_id'] == report['batch_id']
    assert len(client.get('/api/imports').json()['imports']) == 1
    repeated = client.post(f"/api/imports/{report['batch_id']}/confirm", json={'expected_revision':report['revision']}, headers=headers)
    assert repeated.status_code == 200 and repeated.json()['reused']
    assert client.post('/api/imports/preview', files={'file': ('bad.xlsx', b'not an xlsx')}, data=customer_form, headers=headers).status_code == 422
    history = client.get('/api/imports').json()['imports']
    assert len(history) == 2 and history[0]['status'] == 'failed'
    assert not list((LOCAL / 'uploads').iterdir())
    with connect() as conn:
        actions = [r['action'] for r in conn.execute('SELECT action FROM audit_events').fetchall()]
        assert 'import_staged' in actions and 'import_committed' in actions and 'import_replayed' in actions and 'import_rejected' in actions


def test_viewer_cannot_upload_account_disable_revokes_session(environment):
    client, creds = environment
    csrf = sign_in(client, creds)
    with connect() as conn:
        conn.execute("UPDATE staff_accounts SET role='viewer' WHERE username='tester'")
    assert client.post('/api/imports/preview', files={'file': ('bad.xlsx', b'bad')}, headers={'X-CSRF-Token': csrf}).status_code == 403
    assert client.get('/api/audit').status_code == 403
    with connect() as conn:
        conn.execute("UPDATE staff_accounts SET active=false WHERE username='tester'")
    assert client.get('/api/dashboard').status_code == 401


def test_upload_body_limit_before_parsing(environment):
    client, _ = environment
    assert client.post('/api/imports/preview', content=b'x' * (MAX_UPLOAD + 65537), headers={'Content-Type': 'application/octet-stream'}).status_code == 413
