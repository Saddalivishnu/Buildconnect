# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then \
      export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; \
    fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUILDCONNECT_PROJECT_ROOT=/app \
    FLASK_ENV=production

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN --mount=type=secret,id=ca_bundle \
    if [ -s /run/secrets/ca_bundle ]; then \
      export PIP_CERT=/run/secrets/ca_bundle; \
    fi; \
    python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY data/ /app/data/
COPY outputs/ /app/outputs/
COPY models/ /app/models/
COPY --from=frontend /build/frontend/dist/ /app/frontend/dist/

EXPOSE 5000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --timeout 60 deploy_wsgi:app"]
