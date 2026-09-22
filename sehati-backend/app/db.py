from pathlib import Path
import json
import os
import hashlib

import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("SEHATI_STATE_DIR", str(ROOT / ".local")))


def connect():
    url = os.environ.get("SEHATI_DATABASE_URL")
    if not url:
        password_file = os.environ.get("SEHATI_DATABASE_PASSWORD_FILE")
        if password_file:
            url = make_conninfo(host=os.environ.get("SEHATI_DATABASE_HOST", "db"),
                dbname=os.environ.get("SEHATI_DATABASE_NAME", "sehati"),
                user=os.environ.get("SEHATI_DATABASE_USER", "sehati_app"),
                password=Path(password_file).read_text(encoding="utf-8").strip())
        elif os.environ.get("SEHATI_MODE") == "production":
            raise RuntimeError("Production database credentials are missing.")
        else:
            url = json.loads((LOCAL / "runtime.json").read_text(encoding="utf-8-sig"))["database_url"]
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=5)


def initialize():
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(813020)")
        conn.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            name text PRIMARY KEY, checksum text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())""")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            content = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode()).hexdigest()
            applied = conn.execute("SELECT checksum FROM schema_migrations WHERE name=%s", (path.name,)).fetchone()
            if applied:
                if applied["checksum"] != checksum:
                    raise RuntimeError(f"Applied migration was modified: {path.name}. Add a new migration instead.")
                continue
            conn.execute(content)
            conn.execute("INSERT INTO schema_migrations(name,checksum) VALUES(%s,%s)", (path.name, checksum))
