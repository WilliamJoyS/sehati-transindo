from pathlib import Path
from uuid import uuid4
import pytest
from psycopg.types.json import Jsonb
from test_api import environment, sign_in
from app.db import connect
from app import operations


def test_register_preserves_workbook_columns_periods_and_standalone_charge(environment):
    client, creds = environment
    assert client.get('/api/register', params={'customer_id':str(uuid4())}).status_code == 401
    sign_in(client, creds)
    sample=Path('C:/Users/PC/Downloads/BRIDGESTONE 2025.xlsx')
    if not sample.exists(): pytest.skip('Private sample unavailable')
    customer=operations.create_customer({'code':'SHEET','name':'Worksheet test'})
    report=operations.stage_import(sample,sample.name,customer['id'])
    operations.confirm_import(report['batch_id'])
    params={'customer_id':customer['id'],'limit':100}
    invoices=client.get('/api/invoices',params=params).json()['items']
    register=client.get('/api/register',params=params).json()
    assert register['total']==827 and len(invoices)==9
    assert register['items'][0]['source_sheet']=='Sheet1'
    assert register['items'][0]['source_row']==7
    assert {'normal_charge','additional_charge','reported_total','rit_source','source_number'} <= set(register['items'][0])
    total=0; standalone=[]
    for invoice in invoices:
        response=client.get('/api/register',params={**params,'document_id':invoice['id']})
        assert response.status_code==200
        body=response.json(); total+=body['total']
        assert all(r['document_id']==invoice['id'] for r in body['items'])
        standalone += [r for r in body['items'] if r['kind']=='charge']
    assert total==827 and len(standalone)==1
    assert standalone[0]['do_number'] is None and standalone[0]['source_row']==64
    other=operations.create_customer({'code':'OTHER','name':'Other customer'})
    assert client.get('/api/register',params={**params,'customer_id':other['id']}).json()['total']==0
    assert client.get('/api/register',params={**params,'customer_id':other['id'],'document_id':invoices[0]['id']}).status_code==404


def test_disposable_account_delete_revokes_access_retains_history(environment):
    client, creds=environment
    csrf=sign_in(client,creds); headers={'X-CSRF-Token':csrf}
    with connect() as conn:
        user=conn.execute("UPDATE staff_accounts SET deletable=true WHERE username='tester' RETURNING *").fetchone()
        conn.execute("INSERT INTO staff_accounts(id,username,password_hash,totp_encrypted,role) VALUES(%s,'keeper',%s,%s,'admin')",(uuid4(),user['password_hash'],user['totp_encrypted']))
    customer=operations.create_customer({'code':'KEEP','name':'Retained business'},user['id'])
    batch_id=uuid4()
    with connect() as conn:
        conn.execute("INSERT INTO import_batches(id,customer_id,staff_id,filename,file_digest,mapping_version,status,report,staged) VALUES(%s,%s,%s,'test.xlsx','digest','test','preview',%s,%s)",(batch_id,customer['id'],user['id'],Jsonb({}),Jsonb({})))
    issued=client.post('/api/partner-clients',headers=headers,json={'name':'Deletion test','customer_id':customer['id']}).json()
    assert client.get('/api/account').json()['can_delete'] is True
    data={'username':'tester','password':creds['password']}
    assert client.request('DELETE','/api/account',json=data).status_code==403
    assert client.request('DELETE','/api/account',headers=headers,json={**data,'password':'wrong'}).status_code==400
    assert client.request('DELETE','/api/account',headers=headers,json={**data,'username':'keeper'}).status_code==400
    response=client.request('DELETE','/api/account',headers=headers,json=data)
    assert response.status_code==200 and response.json()['deleted']
    assert client.get('/api/account').status_code==401
    assert client.get('/api/partner/v1/status',headers={'X-API-Key':issued['api_key']}).status_code==401
    with connect() as conn:
        assert conn.execute('SELECT 1 FROM staff_accounts WHERE id=%s',(user['id'],)).fetchone() is None
        assert conn.execute('SELECT 1 FROM staff_sessions WHERE staff_id=%s',(user['id'],)).fetchone() is None
        assert conn.execute('SELECT 1 FROM customers WHERE id=%s',(customer['id'],)).fetchone()
        assert conn.execute('SELECT staff_id FROM import_batches WHERE id=%s',(batch_id,)).fetchone()['staff_id'] is None
        assert conn.execute("SELECT 1 FROM audit_events WHERE action='inspection_account_deleted'").fetchone()


def test_protected_and_last_admin_cannot_be_deleted(environment):
    client,creds=environment
    csrf=sign_in(client,creds); headers={'X-CSRF-Token':csrf}
    data={'username':'tester','password':creds['password']}
    assert not client.get('/api/account').json()['can_delete']
    assert client.request('DELETE','/api/account',headers=headers,json=data).status_code==403
    with connect() as conn: conn.execute("UPDATE staff_accounts SET deletable=true WHERE username='tester'")
    assert client.request('DELETE','/api/account',headers=headers,json=data).status_code==409
    assert client.get('/api/account').status_code==200
