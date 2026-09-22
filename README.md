# Sehati Hutama Transindo

Company profile website, protected staff portal, Excel import workflow and customer-scoped partner API for PT. Sehati Hutama Transindo.

## Project structure

- `sehati-transindo/`: public HTML/CSS/JavaScript website and optimized local images. Includes the fleet photos supplied in `foto baru.zip` on 22 September 2026.
- `sehati-backend/`: FastAPI application, staff interface, PostgreSQL schema/migrations and tests.
- `deploy/`: configuration, migration, admin activation, health and backup utilities.
- `compose.yaml`, `Dockerfile`, `Caddyfile`: single-VPS deployment with private PostgreSQL and HTTPS.
- `compose.override.yaml`: resource limits for the current small VPS.

## Deployment

Follow [PANDUAN-VPS.md](PANDUAN-VPS.md) for a **new** Ubuntu 22.04/24.04 server. See [DEPLOYMENT-VPS.md](DEPLOYMENT-VPS.md) for the current deployment and operational limitations, and [API-PARTNER.md](API-PARTNER.md) for API usage.

The private migration backup and authenticator encryption key are transferred separately; they are intentionally absent from this repository. The setup restores existing staff accounts and activates an existing administrator. It does not include a shared default password or automatically create a new administrator.

Do not repeat the initial restore on the running production database. To update an existing deployment, first create a verified backup, update the application source, then rebuild the app:

```sh
cd /opt/sehati
sudo python3 deploy/manage.py backup
# Update the source here without overwriting .env, secrets, migration or volumes.
sudo docker compose build app
sudo docker compose up -d --no-deps --wait app
sudo python3 deploy/health_check.py
```

Do not run `docker compose down -v`: it removes persistent volumes. Pushing to this repository does **not** automatically deploy to the VPS; no deployment automation is configured.

## Security and data

Staff use individual accounts, passwords and Google Authenticator. Partner keys are revocable and limited to one customer and an explicit field list. API responses use committed PostgreSQL records. No external Bridgestone/blockchain service is connected.

Database dumps, business workbooks, passwords, MFA secrets/recovery codes, SSH keys and runtime configuration must remain outside Git. Local verified backups are scheduled on the VPS; automatic off-server backup and external alert delivery still require configuration.

## Image sources

See [image source notes](sehati-transindo/ASSET-LICENSES.md). User-supplied images and third-party source references are distinguished from licensed stock photographs. No blanket open-source or image reuse license is granted by this repository.
