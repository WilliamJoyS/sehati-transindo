"""Local operational API. Run using scripts/start-local.ps1."""
from contextlib import asynccontextmanager
import asyncio
import ipaddress
from pathlib import Path
import tempfile
import threading
from uuid import UUID, uuid4
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import auth
from .db import ROOT, LOCAL, connect, initialize
from .workbook import WorkbookValidationError
from . import operations
from .partner import router as partner_router
from .staff_views import router as staff_views_router
from .authenticator import router as authenticator_router
from .settings import PRODUCTION, ALLOWED_HOSTS, ORIGINS, PUBLIC_ORIGIN

MAX_UPLOAD = 10 * 1024 * 1024
PARSE_LOCK = threading.Lock()
SITE = ROOT.parent / "sehati-transindo"


class BodyLimitMiddleware:
    """Bound bytes before multipart parsing, including chunked requests."""
    def __init__(self, app):
        self.application = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.application(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > MAX_UPLOAD + 65536:
                return await JSONResponse({"detail": "Maximum upload size is 10 MB."}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(chunks)

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        await self.application(scope, replay, send)


@asynccontextmanager
async def lifespan(app):
    initialize()
    if PRODUCTION:
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM staff_accounts WHERE active AND role='admin' LIMIT 1").fetchone():
                raise RuntimeError("Activate the existing production administrator before starting the website.")
    (LOCAL / "uploads").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Sehati · Logistics API", version="1.0.0",
    description="Local end-to-end customer, Excel import, committed delivery, and scoped partner API. This is Sehati's API contract; no external Bridgestone service is connected.",
    lifespan=lifespan, docs_url=None if PRODUCTION else "/docs",
    redoc_url=None if PRODUCTION else "/redoc",
    openapi_url=None if PRODUCTION else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(BodyLimitMiddleware)


if PRODUCTION:
    from fastapi.openapi.docs import get_swagger_ui_html

    @app.get("/openapi.json", include_in_schema=False)
    def protected_schema(request: Request):
        user = auth.session(request)
        if user["role"] != "admin":
            raise HTTPException(403, "Administrator only.")
        return JSONResponse(app.openapi(), headers={"Cache-Control": "no-store"})

    @app.get("/docs", include_in_schema=False)
    def protected_docs(request: Request):
        user = auth.session(request)
        if user["role"] != "admin":
            raise HTTPException(403, "Administrator only.")
        return get_swagger_ui_html(openapi_url="/openapi.json", title="Sehati API")


@app.exception_handler(operations.OperationsError)
async def operation_error(request, exc):
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(WorkbookValidationError)
async def workbook_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.middleware("http")
async def local_security(request, call_next):
    try:
        local = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        local = False
    if not PRODUCTION and not local:
        return JSONResponse({"detail": "This local build only accepts loopback clients."}, status_code=403)
    if PRODUCTION:
        # Caddy overwrites this header. The app publishes NO host port, and runs
        # with --no-proxy-headers. Direct access is confined to the Docker network.
        health_probe = local and request.url.path == "/api/health"
        if not health_probe and (request.headers.get("x-forwarded-proto") != "https"
                or request.headers.get("host") != PUBLIC_ORIGIN.removeprefix("https://")):
            return JSONResponse({"detail": "Use the configured HTTPS domain."}, status_code=400)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") not in ORIGINS:
            return JSONResponse({"detail": "Origin not allowed."}, status_code=403)
        try:
            too_large = int(request.headers.get("content-length", "0")) > MAX_UPLOAD + 65536
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse({"detail": "Maximum upload size is 10 MB."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Request-ID"] = uuid4().hex
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith(("/admin", "/api")):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/admin"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    recovery_code: str | None = Field(default=None, min_length=20, max_length=80)

    @model_validator(mode='after')
    def one_factor(self):
        if bool(self.totp) == bool(self.recovery_code):
            raise ValueError('Masukkan satu kode autentikator atau satu kode pemulihan.')
        return self


@app.get("/api/health", tags=["System"])
def health():
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "unavailable", "mode": "local-operational"}, status_code=503)
    return {"status": "ok", "database": "postgresql", "mode": "production" if PRODUCTION else "local-operational", "commit_enabled": True, "partner_enabled": True, "external_partner_connected": False}


@app.get("/api/session", tags=["Staff"])
def current_session(request: Request):
    return auth.public_session(auth.session(request, required=False))


@app.post("/api/auth/login", tags=["Staff"])
def login(data: Login, request: Request):
    token, user = auth.authenticate(data.username, data.password, data.totp, data.recovery_code)
    old = request.cookies.get(auth.COOKIE)
    if old:
        with connect() as conn:
            conn.execute("DELETE FROM staff_sessions WHERE token_hash=%s", (auth.digest(old),))
    return auth.session_response(token, user)


@app.post("/api/auth/logout", tags=["Staff"])
def logout(request: Request):
    user = auth.require_write(request, roles=("admin", "importer", "viewer"))
    with connect() as conn:
        conn.execute("DELETE FROM staff_sessions WHERE token_hash=%s", (user["token_hash"],))
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'logout')", (user["id"],))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(auth.COOKIE, path="/", secure=PRODUCTION, httponly=True, samesite="strict")
    return response


def json_response(value, status_code=200):
    return JSONResponse(jsonable_encoder(value, custom_encoder={Decimal: str}), status_code=status_code)


class CustomerInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmationInput(BaseModel):
    expected_revision: int = Field(ge=1)


@app.get("/api/customers", tags=["Customers"])
def customers(request: Request):
    auth.session(request)
    return json_response({"customers": operations.list_customers()})


@app.post("/api/customers", tags=["Customers"], status_code=201)
def customer_create(data: CustomerInput, request: Request):
    user = auth.require_write(request, roles=("admin",))
    return json_response(operations.create_customer(data.model_dump(), user["id"]), status_code=201)


@app.get("/api/dashboard", tags=["Staff"])
def dashboard(request: Request, customer_id: UUID | None = None):
    auth.session(request)
    with connect() as conn:
        if customer_id:
            customer = conn.execute("SELECT * FROM customers WHERE id=%s AND active", (customer_id,)).fetchone()
            if not customer:
                raise HTTPException(404, "Pelanggan tidak ditemukan.")
            recent = conn.execute("SELECT report FROM import_batches WHERE customer_id=%s ORDER BY created_at DESC LIMIT 1", (customer_id,)).fetchone()
            business = conn.execute("""SELECT
                (SELECT count(*) FROM deliveries WHERE customer_id=%s) AS deliveries,
                (SELECT count(*) FROM billing_documents WHERE customer_id=%s) AS invoices,
                (SELECT count(*) FROM invoice_lines l JOIN billing_documents b ON b.id=l.billing_document_id WHERE b.customer_id=%s) AS charges""", (customer_id, customer_id, customer_id)).fetchone()
            business["data_version"] = customer["data_version"]
        else:
            recent = conn.execute("SELECT report FROM import_batches ORDER BY created_at DESC LIMIT 1").fetchone()
            business = conn.execute("""SELECT (SELECT count(*) FROM deliveries) AS deliveries,
                (SELECT count(*) FROM billing_documents) AS invoices,
                (SELECT count(*) FROM invoice_lines) AS charges""").fetchone()
            business["data_version"] = None
    report = recent["report"] if recent else {"source": None, "summary": {"sheets": 0, "do_rows": 0, "distinct_do": 0, "issue_count": 0}, "periods": [], "issues": []}
    return json_response({**report, "mode": "production" if PRODUCTION else "local-operational", "database": "postgresql", "imports": operations.list_batches(customer_id), "business": business,
            "partner": {"enabled": True, "external_connected": False, "reason": "API Sehati aktif untuk pengujian lokal dengan kredensial per pelanggan. Belum terhubung ke sistem eksternal Bridgestone."}})


@app.get("/api/deliveries", tags=["Committed records"])
def deliveries(request: Request, customer_id: UUID | None = None,
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
    auth.session(request)
    return json_response(operations.list_deliveries(customer_id, limit, offset))


@app.get("/api/exports/workbook", tags=["Committed records"])
def export_workbook(request: Request, customer_id: UUID):
    user = auth.session(request)
    content = operations.export_workbook(customer_id)
    with connect() as conn:
        conn.execute("INSERT INTO audit_events(actor_id,action,object_id) VALUES(%s,'workbook_exported',%s)", (user["id"], str(customer_id)))
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="sehati-{customer_id}-editable.xlsx"'})


@app.get("/api/imports", tags=["Import previews"])
def imports(request: Request, customer_id: UUID | None = None):
    auth.session(request)
    return json_response({"imports": operations.list_batches(customer_id)})


@app.get("/api/imports/{batch_id}", tags=["Import previews"])
def import_detail(batch_id: UUID, request: Request):
    auth.session(request)
    return json_response(operations.get_batch(batch_id))


@app.get("/api/imports/{batch_id}/rows", tags=["Import previews"])
def import_rows(batch_id: UUID, request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    auth.session(request)
    return json_response(operations.get_batch_rows(batch_id,limit,offset))


@app.get("/api/invoices", tags=["Committed records"])
def invoices(request: Request, customer_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    auth.session(request)
    with connect() as conn:
        total=conn.execute('SELECT count(*) AS n FROM billing_documents WHERE customer_id=%s',(customer_id,)).fetchone()['n']
        rows=conn.execute('SELECT * FROM billing_documents WHERE customer_id=%s ORDER BY period_start DESC,id LIMIT %s OFFSET %s',(customer_id,limit,offset)).fetchall()
    return json_response({'items':rows,'total':total,'limit':limit,'offset':offset})


@app.get("/api/invoice-lines", tags=["Committed records"])
def invoice_lines(request: Request, customer_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    auth.session(request)
    with connect() as conn:
        total=conn.execute('SELECT count(*) AS n FROM invoice_lines WHERE customer_id=%s',(customer_id,)).fetchone()['n']
        rows=conn.execute('SELECT l.*,b.invoice_number FROM invoice_lines l JOIN billing_documents b ON b.id=l.billing_document_id WHERE l.customer_id=%s ORDER BY b.period_start,l.id LIMIT %s OFFSET %s',(customer_id,limit,offset)).fetchall()
    return json_response({'items':rows,'total':total,'limit':limit,'offset':offset})


@app.post("/api/imports/preview", tags=["Import previews"])
async def preview(request: Request, file: UploadFile = File(...), customer_id: UUID | None = Form(None)):
    user = await run_in_threadpool(auth.require_write, request)
    if not customer_id:
        raise HTTPException(422, "Pilih pelanggan sebelum mengunggah workbook.")
    filename = Path((file.filename or "upload.xlsx").replace("\\", "/")).name[:180]
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Gunakan berkas Excel .xlsx.")
    with tempfile.NamedTemporaryFile(dir=LOCAL / "uploads", suffix=".xlsx", delete=False) as temp:
        path = Path(temp.name)
        size = 0
        try:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Berkas melebihi batas 10 MB.")
                temp.write(chunk)
        except BaseException:
            temp.close()
            path.unlink(missing_ok=True)
            raise
        finally:
            temp.close()
            await file.close()
        try:
            if not PARSE_LOCK.acquire(blocking=False):
                raise HTTPException(429, "Satu berkas sedang diperiksa. Coba lagi setelah selesai.")
            try:
                report = await run_in_threadpool(operations.stage_import, path, filename, customer_id, user["id"])
                return json_response(report)
            finally:
                PARSE_LOCK.release()
        finally:
            path.unlink(missing_ok=True)


@app.post("/api/imports/{batch_id}/confirm", tags=["Import previews"])
def confirm(batch_id: UUID, data: ConfirmationInput, request: Request):
    user = auth.require_write(request)
    return json_response(operations.confirm_import(batch_id, user["id"], data.expected_revision))


@app.get("/api/audit", tags=["Staff"])
def audit(request: Request):
    user = auth.session(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Hanya administrator dapat melihat audit.")
    with connect() as conn:
        rows = conn.execute("SELECT e.id,e.action,e.object_id,e.created_at,a.username FROM audit_events e LEFT JOIN staff_accounts a ON a.id=e.actor_id ORDER BY e.id DESC LIMIT 100").fetchall()
    return {"events": [{**r, "created_at": r["created_at"].isoformat()} for r in rows]}


app.include_router(partner_router)
app.include_router(staff_views_router)
app.include_router(authenticator_router)


@app.get("/admin", include_in_schema=False)
def admin():
    return RedirectResponse("/admin/")


app.mount("/admin", StaticFiles(directory=ROOT / "admin", html=True), name="admin-assets")
app.mount("/", StaticFiles(directory=SITE, html=True), name="website")
