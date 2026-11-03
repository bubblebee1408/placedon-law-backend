# Local development image: the gateway, its worker and the test gate (compose.yaml).
# Production does not run this image; it runs a zip on Azure App Service (docs/START_HERE.md §8).
# The source is bind-mounted at /app, so this image holds only the pinned dependencies.
FROM python:3.12-slim-trixie
# git: the engine names its commit (`git rev-parse HEAD`) and refuses to answer without one.
# postgresql-client: pg_dump for scripts/migrate.py's backup-before-apply, psql for bootstrap.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'
WORKDIR /app
COPY requirements.txt requirements-dev.txt requirements-gateway.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check \
      -r requirements-dev.txt -r requirements-gateway.txt
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
