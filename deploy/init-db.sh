#!/bin/sh
set -eu
APP_DB_PASSWORD="$(cat /run/secrets/app_db_password)"
export APP_DB_PASSWORD
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password APP_DB_PASSWORD
CREATE ROLE sehati_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE sehati OWNER TO sehati_app;
ALTER SCHEMA public OWNER TO sehati_app;
SQL
unset APP_DB_PASSWORD
