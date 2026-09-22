"""Partner contract tests use isolated databases and synthetic business records."""
import hashlib
import importlib.util
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.db import ROOT, connect
from app.partner import MANDATORY_FIELDS
from test_api import environment, sign_in


@pytest.fixture()
def partner_environment(environment):
    client, credentials = environment
    csrf = sign_in(client, credentials)
    customer, foreign_customer, document, foreign_document = [uuid4() for _ in range(4)]
    records = [uuid4() for _ in range(4)]
    with connect() as conn:
        for identifier, code in ((customer, 'SYNTHETIC_A'), (foreign_customer, 'SYNTHETIC_B')):
            conn.execute('INSERT INTO customers(id,code,name,data_version) VALUES(%s,%s,%s,7)',
                         (identifier, code, code))
        for identifier, owner in ((document, customer), (foreign_document, foreign_customer)):
            conn.execute("""INSERT INTO billing_documents(id,customer_id,invoice_number,period_start,period_end)
                VALUES(%s,%s,'SYNTHETIC/01','2025-01-01','2025-01-31')""", (identifier, owner))
        for index, record_id in enumerate(records):
            owner, doc = (foreign_customer, foreign_document) if index == 3 else (customer, document)
            conn.execute("""INSERT INTO deliveries(id,customer_id,source_document_id,do_number,vehicle_plate,
                load_date,origin,destination,quantity,volume_m3,notes,distributor)
                VALUES(%s,%s,%s,%s,'TEST-PLATE','2025-01-02','Origin','Destination',4,1.25,
                       'PRIVATE INTERNAL NOTE','PRIVATE DISTRIBUTOR')""", (record_id, owner, doc, f'SYN-{index}'))
    return client, csrf, customer, foreign_customer, records


def make_key(client, csrf, customer, **options):
    response = client.post('/api/partner-clients', headers={'X-CSRF-Token': csrf},
                           json={'name': 'Synthetic local client', 'customer_id': str(customer), **options})
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload, {'X-API-Key': payload['api_key']}


def test_key_is_once_only_hashed_scoped_and_read_only(partner_environment):
    client, csrf, customer, foreign_customer, records = partner_environment
    payload, key_header = make_key(client, csrf, customer, allowed_fields=['do_number', 'volume_m3'])
    key = payload['api_key']
    assert key.startswith('sht_local_')
    assert 'key_digest' not in payload['client']
    listing = client.get('/api/partner-clients')
    assert key not in listing.text and 'key_digest' not in listing.text
    with connect() as conn:
        row = conn.execute('SELECT * FROM api_clients WHERE id=%s', (payload['client']['id'],)).fetchone()
        assert row['key_digest'] == hashlib.sha256(key.encode()).hexdigest()
        assert key not in str(row)
        audits = str(conn.execute('SELECT * FROM audit_events').fetchall())
        assert key not in audits and row['key_digest'] not in audits
    response = client.get('/api/partner/v1/deliveries', headers=key_header)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    result = response.json()
    assert result['meta']['total'] == 3
    assert result['meta']['customer_id'] == str(customer)
    assert {row['id'] for row in result['data']} == {str(identifier) for identifier in records[:3]}
    for row in result['data']:
        assert set(row) == {'do_number', 'volume_m3', *MANDATORY_FIELDS}
        assert row['volume_m3'] == '1.250000'
    assert client.get(f'/api/partner/v1/deliveries/{records[0]}', headers=key_header).status_code == 200
    assert client.get(f'/api/partner/v1/deliveries/{records[3]}', headers=key_header).status_code == 404
    assert client.get('/api/partner/v1/deliveries', headers=key_header,
                      params={'customer_id': str(foreign_customer)}).status_code == 422
    assert client.get('/api/partner/v1/deliveries', headers=key_header,
                      params={'fields': 'notes'}).status_code == 422
    assert client.post('/api/partner/v1/deliveries', headers=key_header, json={}).status_code == 405
    client.cookies.clear()
    assert client.get('/api/partner-clients', headers=key_header).status_code == 401
    assert client.get('/api/deliveries', headers=key_header).status_code == 401
    assert client.get('/api/partner/v1/deliveries').status_code == 401


def test_default_allowlist_and_credentials_admin_permissions(partner_environment):
    client, csrf, customer, _, _ = partner_environment
    for fields in (['notes'], ['reported_total'], [], ['id; DROP TABLE deliveries']):
        result = client.post('/api/partner-clients', headers={'X-CSRF-Token': csrf},
                             json={'name': 'Synthetic client', 'customer_id': str(customer), 'allowed_fields': fields})
        assert result.status_code == 422
    payload, key_header = make_key(client, csrf, customer)
    row = client.get('/api/partner/v1/deliveries', headers=key_header).json()['data'][0]
    assert not {'notes', 'reported_total', 'normal_charge', 'additional_charge',
                'vehicle_plate', 'distributor', 'transporter'} & set(row)
    assert client.post('/api/partner-clients', json={'name': 'No CSRF', 'customer_id': str(customer)}).status_code == 403
    for days in (0, 366):
        assert client.post('/api/partner-clients', headers={'X-CSRF-Token': csrf},
                           json={'name': 'Bad expiry', 'customer_id': str(customer), 'expires_in_days': days}).status_code == 422
    with connect() as conn:
        conn.execute("UPDATE staff_accounts SET role='importer' WHERE username='tester'")
    assert client.get('/api/partner-clients').status_code == 403
    assert client.post('/api/partner-clients', headers={'X-CSRF-Token': csrf},
                       json={'name': 'No permission', 'customer_id': str(customer)}).status_code == 403
    assert client.post(f"/api/partner-clients/{payload['client']['id']}/revoke", headers={'X-CSRF-Token': csrf}).status_code == 403


def test_revoke_expiry_customer_disable_and_scope_fail_closed(partner_environment):
    client, csrf, customer, _, _ = partner_environment
    payload, key_header = make_key(client, csrf, customer)
    identifier = payload['client']['id']
    status = client.get('/api/partner/v1/status', headers=key_header)
    assert status.status_code == 200 and status.json()['external_partner_connected'] is False
    assert client.post(f'/api/partner-clients/{identifier}/revoke').status_code == 403
    for _ in range(2):
        assert client.post(f'/api/partner-clients/{identifier}/revoke', headers={'X-CSRF-Token': csrf}).status_code == 200
    assert client.get('/api/partner/v1/status', headers=key_header).status_code == 401
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM audit_events WHERE action='partner_client_revoked'").fetchone()['n'] == 1
    payload, key_header = make_key(client, csrf, customer)
    identifier = payload['client']['id']
    with connect() as conn:
        conn.execute("UPDATE api_clients SET expires_at=now()-interval '1 second' WHERE id=%s", (identifier,))
    assert client.get('/api/partner/v1/deliveries', headers=key_header).status_code == 401
    with connect() as conn:
        conn.execute("UPDATE api_clients SET expires_at=now()+interval '1 day',scopes=ARRAY[]::text[] WHERE id=%s", (identifier,))
    assert client.get('/api/partner/v1/deliveries', headers=key_header).status_code == 403
    with connect() as conn:
        conn.execute("UPDATE api_clients SET scopes=ARRAY['deliveries:read'] WHERE id=%s", (identifier,))
        conn.execute('UPDATE customers SET active=false WHERE id=%s', (customer,))
    assert client.get('/api/partner/v1/deliveries', headers=key_header).status_code == 401
    assert client.get('/api/partner/v1/status', headers={'X-API-Key': 'x' * 80}).status_code == 401


def test_pagination_requires_unchanged_database_snapshot(partner_environment):
    client, csrf, customer, _, records = partner_environment
    _, key_header = make_key(client, csrf, customer)
    page_one = client.get('/api/partner/v1/deliveries?limit=2', headers=key_header).json()
    assert page_one['meta']['next_offset'] == 2
    assert client.get('/api/partner/v1/deliveries?offset=2', headers=key_header).status_code == 422
    assert client.get('/api/partner/v1/deliveries?limit=101', headers=key_header).status_code == 422
    params = {'limit': 2, 'offset': 2, 'data_version': page_one['meta']['data_version']}
    page_two = client.get('/api/partner/v1/deliveries', headers=key_header, params=params).json()
    assert page_two['meta']['next_offset'] is None
    assert len({row['id'] for row in page_one['data'] + page_two['data']}) == 3
    with connect() as conn:
        conn.execute('UPDATE customers SET data_version=data_version+1 WHERE id=%s', (customer,))
        conn.execute("UPDATE deliveries SET destination='Changed',version=version+1,updated_at=now() WHERE id=%s", (records[0],))
    conflict = client.get('/api/partner/v1/deliveries', headers=key_header, params=params)
    assert conflict.status_code == 409
    assert conflict.json()['detail']['code'] == 'snapshot_changed'
    assert 'data' not in conflict.json()
    restart = client.get('/api/partner/v1/deliveries', headers=key_header).json()
    assert restart['meta']['data_version'] == page_one['meta']['data_version'] + 1
    assert any(row['destination'] == 'Changed' for row in restart['data'])


def test_rate_limits_are_persistent_per_key_and_reset(partner_environment):
    client, csrf, customer, _, _ = partner_environment
    payload, key_header = make_key(client, csrf, customer)
    with connect() as conn:
        conn.execute("""INSERT INTO partner_rate_limits(client_id,window_start,request_count)
            VALUES(%s,date_trunc('minute',now()),120)""", (payload['client']['id'],))
    response = client.get('/api/partner/v1/status', headers=key_header)
    assert response.status_code == 429 and response.headers['retry-after'] == '60'
    with connect() as conn:
        assert conn.execute('SELECT request_count FROM partner_rate_limits WHERE client_id=%s',
                            (payload['client']['id'],)).fetchone()['request_count'] == 121
    _, other_key = make_key(client, csrf, customer)
    assert client.get('/api/partner/v1/status', headers=other_key).status_code == 200
    with connect() as conn:
        conn.execute("UPDATE partner_rate_limits SET window_start=now()-interval '2 minutes' WHERE client_id=%s", (payload['client']['id'],))
    assert client.get('/api/partner/v1/status', headers=key_header).status_code == 200
    with connect() as conn:
        assert conn.execute('SELECT request_count FROM partner_rate_limits WHERE client_id=%s',
                            (payload['client']['id'],)).fetchone()['request_count'] == 1


def load_inspection_client():
    spec = importlib.util.spec_from_file_location('inspection_partner_client', ROOT / 'scripts' / 'partner_client.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('origin', ['https://example.com', 'http://example.com', 'http://127.0.0.1.evil.test',
                                    'http://user:secret@localhost', 'http://localhost/path', 'http://localhost?key=secret'])
def test_inspection_client_rejects_nonlocal_origins(origin):
    module = load_inspection_client()
    with pytest.raises(ValueError, match='only accepts a local'):
        module.fetch_snapshot(origin, 'never-transmitted')


def test_inspection_client_discards_partial_snapshot_and_uses_no_proxy(monkeypatch):
    module = load_inspection_client()
    calls = []
    def handle(request):
        calls.append(request)
        assert request.headers['X-API-Key'] == 'synthetic-test-key'
        if request.url.path.endswith('/status'):
            return httpx.Response(200, json={'contract': 'sehati-v1'})
        if len(calls) == 2:
            return httpx.Response(200, json={'data': [{'id': 'old'}], 'meta': {'total': 2, 'next_offset': 1, 'data_version': 1}})
        if len(calls) == 3:
            assert request.url.params['data_version'] == '1'
            return httpx.Response(409, json={'detail': {'code': 'snapshot_changed'}})
        assert request.url.params['offset'] == '0' and 'data_version' not in request.url.params
        return httpx.Response(200, json={'data': [{'id': 'new'}], 'meta': {'total': 1, 'next_offset': None, 'data_version': 2}})
    original_client = httpx.Client
    def local_client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original_client(**kwargs, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(module.httpx, 'Client', local_client)
    result = module.fetch_snapshot('http://127.0.0.1:8000', 'synthetic-test-key', limit=1)
    assert result == {'records': 1, 'pages': 1, 'data_version': 2, 'contract': 'sehati-v1', 'external_partner_connected': False}
