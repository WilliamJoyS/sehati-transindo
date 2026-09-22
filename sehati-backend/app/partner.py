"""Sehati's proposed partner v1 API, exercised locally without external delivery.

Only committed PostgreSQL records are visible. Each client is permanently scoped
to one customer and an explicit field allowlist. The actual partner contract is
not asserted here. Pagination is a version-checked full snapshot, not a delta API.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg import sql
from psycopg.types.json import Jsonb

from . import auth
from .db import connect

router = APIRouter()
RATE_LIMIT = 120
MANDATORY_FIELDS = ("id", "version", "updated_at")
DEFAULT_FIELDS = (
    "id", "do_number", "load_date", "estimated_unload_date", "actual_unload_date",
    "origin", "destination", "quantity", "volume_m3", "version", "updated_at",
)
ALLOWED_FIELDS = DEFAULT_FIELDS + (
    "vehicle_plate", "distributor", "capacity_m3", "vehicle_type", "transporter",
)
API_KEY = APIKeyHeader(name="X-API-Key", scheme_name="PartnerApiKey", auto_error=False,
                       description="Customer-scoped key created by a staff administrator. Local contract only.")


class CreateClient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)
    customer_id: UUID
    allowed_fields: list[str] | None = Field(default=None, max_length=len(ALLOWED_FIELDS))
    expires_in_days: int = Field(default=30, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if len(value) < 2 or any(ord(char) < 32 for char in value):
            raise ValueError("Use a descriptive name without control characters.")
        return value

    @field_validator("allowed_fields")
    @classmethod
    def valid_fields(cls, value):
        if value is not None and (not value or any(field not in ALLOWED_FIELDS for field in value)):
            raise ValueError("Only explicitly supported delivery fields may be shared.")
        return value


def serialized(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def public_client(row):
    fields = ("id", "name", "customer_id", "customer_name", "key_hint", "scopes",
              "allowed_fields", "active", "expires_at", "created_at", "revoked_at", "last_used_at")
    return {field: serialized(row.get(field)) for field in fields}


def admin_user(request, write=False):
    user = auth.require_write(request, roles=("admin",)) if write else auth.session(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Hanya administrator dapat mengelola kredensial partner.")
    return user


@router.get("/api/partner-clients", tags=["Partner credential administration"])
def list_clients(request: Request):
    admin_user(request)
    with connect() as conn:
        rows = conn.execute("""SELECT a.*,c.name AS customer_name FROM api_clients a
            JOIN customers c ON c.id=a.customer_id ORDER BY a.created_at DESC LIMIT 200""").fetchall()
    return {"clients": [public_client(row) for row in rows], "default_fields": DEFAULT_FIELDS,
            "available_fields": ALLOWED_FIELDS, "mandatory_fields": MANDATORY_FIELDS,
            "contract_status": "sehati_v1" if auth.PRODUCTION else "sehati_v1_local", "external_partner_connected": False}


@router.post("/api/partner-clients", tags=["Partner credential administration"], status_code=201)
def create_client(data: CreateClient, request: Request):
    user = admin_user(request, write=True)
    prefix = "sht_" if auth.PRODUCTION else "sht_local_"
    key = prefix + secrets.token_urlsafe(48)
    fields = list(dict.fromkeys([*(data.allowed_fields if data.allowed_fields is not None else DEFAULT_FIELDS), *MANDATORY_FIELDS]))
    with connect() as conn:
        customer = conn.execute("SELECT id,name FROM customers WHERE id=%s AND active", (data.customer_id,)).fetchone()
        if not customer:
            raise HTTPException(422, "Pelanggan aktif tidak ditemukan.")
        row = conn.execute("""INSERT INTO api_clients
            (id,name,customer_id,key_digest,key_hint,allowed_fields,expires_at,created_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (uuid4(), data.name, data.customer_id, hashlib.sha256(key.encode()).hexdigest(),
             prefix + "…" + key[-6:], fields,
             datetime.now(timezone.utc) + timedelta(days=data.expires_in_days), user["id"])).fetchone()
        conn.execute("INSERT INTO audit_events(actor_id,action,object_id,details) VALUES(%s,'partner_client_created',%s,%s)",
                     (user["id"], str(row["id"]), Jsonb({"customer_id": str(data.customer_id), "allowed_fields": fields})))
    row["customer_name"] = customer["name"]
    return {"client": public_client(row), "api_key": key,
            "message": "Simpan kunci ini di tempat privat. Kunci hanya ditampilkan satu kali; belum dikirim ke partner."}


@router.post("/api/partner-clients/{client_id}/revoke", tags=["Partner credential administration"])
def revoke_client(client_id: UUID, request: Request):
    user = admin_user(request, write=True)
    with connect() as conn:
        row = conn.execute("SELECT * FROM api_clients WHERE id=%s FOR UPDATE", (client_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Kredensial partner tidak ditemukan.")
        if row["active"]:
            conn.execute("UPDATE api_clients SET active=false,revoked_at=now() WHERE id=%s", (client_id,))
            conn.execute("INSERT INTO audit_events(actor_id,action,object_id) VALUES(%s,'partner_client_revoked',%s)",
                         (user["id"], str(client_id)))
    return {"id": str(client_id), "active": False}


def authenticate_partner(key: Annotated[str | None, Security(API_KEY)]):
    denied = HTTPException(401, "Kunci API tidak valid, kedaluwarsa, atau telah dicabut.", headers={"WWW-Authenticate": "ApiKey"})
    if not key or not (40 <= len(key) <= 128):
        raise denied
    with connect() as conn:
        client = conn.execute("""SELECT a.* FROM api_clients a JOIN customers c ON c.id=a.customer_id
            WHERE a.key_digest=%s AND a.active AND a.expires_at>now() AND c.active""",
            (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
        if not client:
            raise denied
        if "deliveries:read" not in client["scopes"]:
            raise HTTPException(403, "Kredensial tidak memiliki izin deliveries:read.")
        bucket = conn.execute("""INSERT INTO partner_rate_limits(client_id,window_start,request_count)
            VALUES(%s,date_trunc('minute',now()),1) ON CONFLICT(client_id) DO UPDATE
            SET window_start=excluded.window_start,
                request_count=CASE WHEN partner_rate_limits.window_start=excluded.window_start
                  THEN least(partner_rate_limits.request_count+1,%s) ELSE 1 END
            RETURNING request_count""", (client["id"], RATE_LIMIT + 1)).fetchone()
        if bucket["request_count"] > RATE_LIMIT:
            conn.commit()
            raise HTTPException(429, "Batas 120 permintaan per menit tercapai.", headers={"Retry-After": "60"})
        conn.execute("UPDATE api_clients SET last_used_at=now() WHERE id=%s", (client["id"],))
    return client


def reject_unknown_query(request, allowed):
    unknown = set(request.query_params) - set(allowed)
    if unknown:
        raise HTTPException(422, "Parameter tidak didukung. Pelanggan dan kolom ditentukan oleh kredensial API.")


def read_fields(client):
    # Revalidate persisted permissions before composing SQL identifiers.
    fields = [field for field in client["allowed_fields"] if field in ALLOWED_FIELDS]
    return list(dict.fromkeys([*fields, *MANDATORY_FIELDS]))


@router.get("/api/partner/v1/status", tags=["Partner v1 — local contract"])
def partner_status(request: Request, response: Response, client: Annotated[dict, Depends(authenticate_partner)]):
    reject_unknown_query(request, ())
    response.headers["Cache-Control"] = "no-store"
    with connect() as conn:
        row = conn.execute("SELECT data_version FROM customers WHERE id=%s", (client["customer_id"],)).fetchone()
    return {"status": "ready", "contract": "sehati-v1", "mode": "production" if auth.PRODUCTION else "local",
            "external_partner_connected": False, "customer_id": str(client["customer_id"]),
            "scope": "deliveries:read", "allowed_fields": read_fields(client),
            "data_version": row["data_version"], "pagination": "version_checked_full_snapshot",
            "rate_limit_per_minute": RATE_LIMIT}


@router.get("/api/partner/v1/deliveries", tags=["Partner v1 — local contract"],
            description="Read committed deliveries for this credential's customer. Send data_version returned by page one on every later page. On HTTP 409 discard partial results and restart from offset zero. No financial fields or internal notes are exposed.")
def partner_deliveries(request: Request, response: Response,
                       client: Annotated[dict, Depends(authenticate_partner)],
                       limit: int = Query(default=50, ge=1, le=100),
                       offset: int = Query(default=0, ge=0, le=1000000),
                       data_version: int | None = Query(default=None, ge=0)):
    reject_unknown_query(request, ("limit", "offset", "data_version"))
    if offset and data_version is None:
        raise HTTPException(422, "Halaman berikutnya memerlukan data_version dari halaman pertama.")
    response.headers["Cache-Control"] = "no-store"
    fields = read_fields(client)
    with connect() as conn:
        # Revision, count and rows must all describe one database snapshot.
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        revision = conn.execute("SELECT data_version FROM customers WHERE id=%s", (client["customer_id"],)).fetchone()["data_version"]
        if data_version is not None and revision != data_version:
            raise HTTPException(409, {"code": "snapshot_changed", "message": "Data berubah. Buang hasil sebagian dan mulai kembali dari offset 0.", "data_version": revision})
        total = conn.execute("SELECT count(*) AS n FROM deliveries WHERE customer_id=%s", (client["customer_id"],)).fetchone()["n"]
        query = sql.SQL("SELECT {} FROM deliveries WHERE customer_id=%s ORDER BY id LIMIT %s OFFSET %s").format(
            sql.SQL(",").join(map(sql.Identifier, fields)))
        rows = conn.execute(query, (client["customer_id"], limit, offset)).fetchall()
    return {"data": [{field: serialized(row[field]) for field in fields} for row in rows],
            "meta": {"total": total, "limit": limit, "offset": offset,
                     "next_offset": offset + len(rows) if offset + len(rows) < total else None,
                     "data_version": revision, "customer_id": str(client["customer_id"])}}


@router.get("/api/partner/v1/deliveries/{delivery_id}", tags=["Partner v1 — local contract"])
def partner_delivery(delivery_id: UUID, request: Request, response: Response,
                     client: Annotated[dict, Depends(authenticate_partner)]):
    reject_unknown_query(request, ())
    response.headers["Cache-Control"] = "no-store"
    fields = read_fields(client)
    with connect() as conn:
        query = sql.SQL("SELECT {} FROM deliveries WHERE id=%s AND customer_id=%s").format(
            sql.SQL(",").join(map(sql.Identifier, fields)))
        row = conn.execute(query, (delivery_id, client["customer_id"])).fetchone()
    if not row:
        raise HTTPException(404, "Pengiriman tidak ditemukan.")
    return {"data": {field: serialized(row[field]) for field in fields}}
