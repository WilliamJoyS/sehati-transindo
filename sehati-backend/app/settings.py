"""Explicit local/production configuration; production fails closed."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.fernet import Fernet

MODE = os.environ.get("SEHATI_MODE", "local")
if MODE not in {"local", "production"}:
    raise RuntimeError("SEHATI_MODE must be local or production.")
PRODUCTION = MODE == "production"
PUBLIC_ORIGIN = os.environ.get("SEHATI_PUBLIC_ORIGIN", "").rstrip("/")
if PRODUCTION:
    parsed = urlsplit(PUBLIC_ORIGIN)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.netloc != host or parsed.path
            or parsed.query or parsed.fragment or "." not in host
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
            or host in {"127.0.0.1", "localhost"}):
        raise RuntimeError("Set SEHATI_PUBLIC_ORIGIN to the exact HTTPS domain, without a port/path.")
    ENCRYPTION_KEY_FILE = Path(os.environ["SEHATI_ENCRYPTION_KEY_FILE"])
    Fernet(ENCRYPTION_KEY_FILE.read_text(encoding="utf-8").strip().encode())
    ALLOWED_HOSTS = [host, "127.0.0.1", "localhost"]
    ORIGINS = {PUBLIC_ORIGIN}
else:
    ENCRYPTION_KEY_FILE = None
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    ORIGINS = {"http://127.0.0.1:8000", "http://localhost:8000"}
