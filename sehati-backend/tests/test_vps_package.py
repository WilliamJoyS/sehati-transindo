"""Production settings and isolation checks using the existing isolated-DB fixture."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest
from test_api import environment
from app.db import LOCAL, connect

PACKAGE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vps_configure", PACKAGE / "deploy" / "configure.py")
configure_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure_module)
manage_spec = importlib.util.spec_from_file_location("vps_manage", PACKAGE / "deploy" / "manage.py")
manage_module = importlib.util.module_from_spec(manage_spec)
manage_spec.loader.exec_module(manage_module)


def test_configure_preserves_imported_key_and_refuses_overwrite(tmp_path):
    original = tmp_path / "imported.key"
    raw = base64.urlsafe_b64encode(os.urandom(32)).decode()
    original.write_text(raw)
    output = tmp_path / "package"
    output.mkdir()
    configure_module.configure(output, "logistics.example.test", "admin@example.test", original)
    assert (output / "secrets" / "authenticator_key").read_text().strip() == raw
    assert len((output / "secrets" / "app_db_password").read_text().strip()) == 64
    assert raw not in (output / ".env").read_text()
    password = (output / "secrets" / "app_db_password").read_text()
    with pytest.raises(ValueError):
        configure_module.configure(output, "other.example.test", "admin@example.test", original)
    assert (output / "secrets" / "app_db_password").read_text() == password


@pytest.mark.parametrize("domain", ["http://example.test", "localhost", "127.0.0.1", "a.test/path", "bad\nDOMAIN=evil.test"])
def test_configure_rejects_unsafe_domains(tmp_path, domain):
    with pytest.raises(ValueError):
        configure_module.configure(tmp_path, domain, "admin@example.test", tmp_path / "missing")
    assert not (tmp_path / "secrets").exists()


def test_compose_exposes_only_https_proxy_and_uses_persistent_private_storage():
    config = json.loads((PACKAGE / "compose.yaml").read_text())
    assert "ports" not in config["services"]["db"]
    assert "ports" not in config["services"]["app"]
    assert set(config["services"]["caddy"]["ports"]) == {"80:80", "443:443", "443:443/udp"}
    assert config["networks"]["database"]["internal"] is True
    assert config["networks"]["proxy"]["internal"] is True
    assert "pgdata:/var/lib/postgresql" in config["services"]["db"]["volumes"]
    assert config["services"]["app"]["read_only"] is True
    assert set(config["services"]["app"]["secrets"]) == {"app_db_password", "authenticator_key"}


def test_production_https_hosts_origin_mfa_cookie_and_private_docs(environment, tmp_path):
    client, creds = environment
    key = tmp_path / "key"
    key.write_text(json.loads((LOCAL / "app-secrets.json").read_text())["encryption_key"])
    env = os.environ.copy()
    env.update(SEHATI_MODE="production", SEHATI_PUBLIC_ORIGIN="https://logistics.example.test",
               SEHATI_ENCRYPTION_KEY_FILE=str(key), PYTHONDONTWRITEBYTECODE="1")
    code = r'''
import json,sys
from fastapi.testclient import TestClient
from app.main import app
from app import auth
creds=json.load(sys.stdin)
headers={"Origin":"https://logistics.example.test","X-Forwarded-Proto":"https"}
with TestClient(app,base_url="https://logistics.example.test",client=("172.18.0.4",50000),headers=headers) as c:
    assert c.get("/").status_code==200
    assert c.get("/admin/").status_code==200
    assert c.get("/api/dashboard").status_code==401
    assert c.get("/docs").status_code==401
    assert c.get("/openapi.json").status_code==401
    assert c.get("/",headers={"Host":"evil.example"}).status_code==400
    assert c.get("/",headers={"X-Forwarded-Proto":"http"}).status_code==400
    assert c.post("/api/auth/login",json=creds,headers={"Origin":"https://evil.example"}).status_code==403
    password={"username":creds["username"],"password":creds["password"]}
    r=c.post("/api/auth/authenticator/next",json=password)
    assert r.status_code==200 and r.json()["step"]=="code"
    assert "set-cookie" not in r.headers
    assert c.post("/api/auth/login",json=password).status_code==422
    r=c.post("/api/auth/login",json=creds)
    assert r.status_code==200, r.text
    cookie=r.headers["set-cookie"]
    assert "__Host-sehati_session=" in cookie and "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert c.get("/docs").status_code==200 and c.get("/openapi.json").status_code==200
    r=c.post("/api/auth/logout",headers={"X-CSRF-Token":r.json()["csrf_token"]})
    assert r.status_code==200 and "Secure" in r.headers["set-cookie"]
    assert c.get("/api/dashboard").status_code==401
with TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",50001)) as c:
    assert c.get("/api/health").status_code==200
    assert c.get("/admin/").status_code==400
print("Production boundary checks passed.")
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=PACKAGE / "sehati-backend", env=env,
                            input=json.dumps(creds), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_production_refuses_http_origin(tmp_path):
    env = os.environ.copy()
    env.update(SEHATI_MODE="production", SEHATI_PUBLIC_ORIGIN="http://logistics.example.test")
    result = subprocess.run([sys.executable, "-c", "import app.settings"], cwd=PACKAGE / "sehati-backend",
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0 and "exact HTTPS domain" in result.stderr


def test_migration_accepts_original_json_encryption_key(tmp_path):
    raw = base64.urlsafe_b64encode(os.urandom(32)).decode()
    imported = tmp_path / "app-secrets.json"
    imported.write_text(json.dumps({"encryption_key": raw}))
    folder = tmp_path / "target"
    folder.mkdir()
    configure_module.configure(folder, "logistics.example.test", "admin@example.test", imported)
    assert (folder / "secrets" / "authenticator_key").read_text().strip() == raw


def test_restore_refuses_running_app_or_nonempty_database(monkeypatch, tmp_path):
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"PGDMPtest-placeholder")
    dump.with_suffix(".json").write_text(json.dumps({"sha256":manage_module.sha256(dump)}))
    restore_call = Mock()
    monkeypatch.setattr(manage_module, "restore_dump", restore_call)
    monkeypatch.setattr(manage_module, "compose", Mock(return_value=Mock(stdout="db\napp\n")))
    with pytest.raises(ValueError, match="Stop app"):
        manage_module.restore(dump)
    monkeypatch.setattr(manage_module, "compose", Mock(return_value=Mock(stdout="db\n")))
    monkeypatch.setattr(manage_module, "sql", Mock(return_value="1"))
    with pytest.raises(ValueError, match="not empty"):
        manage_module.restore(dump)
    restore_call.assert_not_called()


def test_migration_disables_old_access_but_preserves_business_records(environment, tmp_path, monkeypatch):
    from test_api import sign_in
    from test_operations import customer, legacy, commit
    client, creds = environment
    cid = customer()
    commit(legacy(tmp_path), cid)
    csrf = sign_in(client, creds)
    response = client.post("/api/partner-clients", headers={"X-CSRF-Token":csrf},
                           json={"name":"Migration test", "customer_id":str(cid)})
    assert response.status_code == 201
    key = response.json()["api_key"]
    def isolated_sql(statement, database="sehati"):
        with connect() as conn:
            conn.execute(statement)
    monkeypatch.setattr(manage_module, "sql", isolated_sql)
    manage_module.sanitize_restored_access()
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/partner/v1/deliveries", headers={"X-API-Key":key}).status_code == 401
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM deliveries").fetchone()["n"] == 2
        assert conn.execute("SELECT count(*) AS n FROM staff_accounts").fetchone()["n"] == 1
        assert conn.execute("SELECT 1 FROM staff_accounts WHERE active").fetchone() is None
        assert conn.execute("SELECT 1 FROM audit_events WHERE action='vps_restore_awaiting_admin_activation'").fetchone()


def test_activate_existing_production_admin_without_creating_accounts(environment, tmp_path):
    client, creds = environment
    key = tmp_path / "key"
    key.write_text(json.loads((LOCAL / "app-secrets.json").read_text())["encryption_key"])
    with connect() as conn:
        original = conn.execute("SELECT id FROM staff_accounts").fetchone()["id"]
        conn.execute("UPDATE staff_accounts SET active=false")
    env = os.environ.copy()
    env.update(SEHATI_MODE="production", SEHATI_PUBLIC_ORIGIN="https://logistics.example.test",
               SEHATI_ENCRYPTION_KEY_FILE=str(key), PYTHONDONTWRITEBYTECODE="1")
    code = r'''
import importlib.util,sys
from pathlib import Path
from unittest.mock import patch
path=Path("..")/"deploy"/"activate_admin.py"
spec=importlib.util.spec_from_file_location("activate_admin",path)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.argv=["activate_admin.py","--username","tester"]
with patch("getpass.getpass",return_value="Only-for-isolated-test-2026!"):
    m.main()
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=PACKAGE / "sehati-backend", env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with connect() as conn:
        rows = conn.execute("SELECT * FROM staff_accounts").fetchall()
        assert len(rows) == 1 and rows[0]["id"] == original and rows[0]["active"]
        assert conn.execute("SELECT 1 FROM mfa_initial_permissions").fetchone()
