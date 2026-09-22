FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/sehati-backend
COPY sehati-backend/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt \
    && groupadd --gid 10001 sehati \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin sehati \
    && mkdir -p /var/lib/sehati/uploads \
    && chown -R sehati:sehati /var/lib/sehati
COPY sehati-backend/app ./app
COPY sehati-backend/admin ./admin
COPY sehati-backend/migrations ./migrations
COPY sehati-backend/schema.sql ./schema.sql
COPY sehati-transindo /srv/sehati-transindo
COPY deploy /srv/deploy
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "40"]
