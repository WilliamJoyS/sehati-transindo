"""Authenticated worksheet view and deletion of explicitly disposable accounts."""
from uuid import UUID
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from . import auth
from .db import connect
from .import_engine import clean

router = APIRouter()


@router.get('/api/register', tags=['Committed records'])
def register(request: Request, customer_id: UUID, document_id: UUID | None = None,
             limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
    auth.session(request)
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if not conn.execute('SELECT 1 FROM customers WHERE id=%s AND active', (customer_id,)).fetchone():
            raise HTTPException(404, 'Pelanggan tidak ditemukan.')
        if document_id and not conn.execute('SELECT 1 FROM billing_documents WHERE id=%s AND customer_id=%s', (document_id, customer_id)).fetchone():
            raise HTTPException(404, 'Periode pelanggan tidak ditemukan.')
        clause = ' AND b.id=%s' if document_id else ''
        params = (customer_id, document_id) if document_id else (customer_id,)
        # Preserve invoice-level charges as separate rows, without fabricating a delivery.
        base = '''WITH records AS (
            SELECT d.id,d.source_document_id AS document_id,'delivery' AS kind,
                d.transporter,d.do_number,d.vehicle_plate,d.load_date,d.estimated_unload_date,
                d.actual_unload_date,d.origin,d.destination,d.distributor,d.capacity_m3,d.vehicle_type,
                d.quantity,d.volume_m3,l.normal_charge,l.additional_charge,l.reported_total,
                COALESCE(l.note,d.notes) AS note,d.version
            FROM deliveries d LEFT JOIN invoice_lines l ON l.delivery_id=d.id AND l.customer_id=d.customer_id
            WHERE d.customer_id=%s
            UNION ALL
            SELECT l.id,l.billing_document_id,'charge',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
                NULL,NULL,l.normal_charge,l.additional_charge,l.reported_total,l.note,l.version
            FROM invoice_lines l WHERE l.customer_id=%s AND l.delivery_id IS NULL
        ) '''
        query_params = (customer_id, customer_id) + params
        total = conn.execute(base + 'SELECT count(*) AS n FROM records r JOIN billing_documents b ON b.id=r.document_id WHERE b.customer_id=%s' + clause, query_params).fetchone()['n']
        rows = conn.execute(base + '''SELECT r.*,b.invoice_number,b.period_start,b.period_end,
            s.sheet AS source_sheet,s.row_number AS source_row,
            s.source_payload->>'No.' AS source_number,s.source_payload->>'Rit' AS rit_source
            FROM records r JOIN billing_documents b ON b.id=r.document_id
            LEFT JOIN LATERAL (SELECT sheet,row_number,source_payload FROM import_rows
                WHERE record_id=r.id AND action='new' ORDER BY id LIMIT 1) s ON true
            WHERE b.customer_id=%s''' + clause + ''' ORDER BY b.period_start,b.invoice_number,
            s.row_number NULLS LAST,r.id LIMIT %s OFFSET %s''', query_params + (limit, offset)).fetchall()
    return {'items': clean(rows), 'total': total, 'limit': limit, 'offset': offset}


@router.get('/api/account', tags=['Staff account'])
def account(request: Request):
    user = auth.session(request)
    with connect() as conn:
        row = conn.execute('SELECT username,role,deletable,authenticator_enrolled_at FROM staff_accounts WHERE id=%s', (user['id'],)).fetchone()
        remaining = conn.execute('SELECT count(*) AS n FROM mfa_recovery_codes WHERE staff_id=%s AND used_at IS NULL', (user['id'],)).fetchone()['n']
    return {'username': row['username'], 'role': row['role'], 'can_delete': row['deletable'],
            'authenticator_enrolled': row['authenticator_enrolled_at'] is not None, 'recovery_codes_remaining': remaining}


class DeleteAccount(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@router.delete('/api/account', tags=['Staff account'])
def delete_account(data: DeleteAccount, request: Request):
    user = auth.require_write(request, roles=('admin', 'importer', 'viewer'))
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(813024)')
        row = conn.execute('SELECT * FROM staff_accounts WHERE id=%s FOR UPDATE', (user['id'],)).fetchone()
        if not row or not row['deletable']:
            raise HTTPException(403, 'Akun ini tidak ditandai sebagai akun inspeksi yang boleh dihapus.')
        recent = conn.execute("SELECT count(*) AS n FROM audit_events WHERE action='account_delete_failed' AND actor_id=%s AND created_at>now()-interval '5 minutes'", (row['id'],)).fetchone()['n']
        if recent >= 5:
            raise HTTPException(429, 'Terlalu banyak percobaan. Tunggu lima menit.')
        if data.username != row['username'] or not auth.PASSWORDS.verify(data.password, row['password_hash']):
            conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'account_delete_failed')", (row['id'],))
            conn.commit()
            raise HTTPException(400, 'Nama pengguna atau kata sandi tidak sesuai.')
        if row['role'] == 'admin' and not conn.execute("SELECT 1 FROM staff_accounts WHERE role='admin' AND active AND id<>%s", (row['id'],)).fetchone():
            raise HTTPException(409, 'Administrator aktif terakhir tidak dapat dihapus.')
        conn.execute("UPDATE api_clients SET active=false,revoked_at=COALESCE(revoked_at,now()),created_by=NULL WHERE created_by=%s", (row['id'],))
        conn.execute('DELETE FROM staff_sessions WHERE staff_id=%s', (row['id'],))
        conn.execute('UPDATE preview_batches SET staff_id=NULL WHERE staff_id=%s', (row['id'],))
        conn.execute('UPDATE import_batches SET staff_id=NULL WHERE staff_id=%s', (row['id'],))
        conn.execute('UPDATE audit_events SET actor_id=NULL WHERE actor_id=%s', (row['id'],))
        conn.execute("INSERT INTO audit_events(action,details) VALUES('inspection_account_deleted',%s)", (Jsonb({'username': row['username']}),))
        conn.execute('DELETE FROM staff_accounts WHERE id=%s', (row['id'],))
    response = JSONResponse({'deleted': True, 'message': 'Akun telah dihapus. Data operasional tetap tersimpan.'})
    response.delete_cookie(auth.COOKIE, path='/', secure=auth.PRODUCTION, httponly=True, samesite='strict')
    return response
