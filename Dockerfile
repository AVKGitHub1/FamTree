# syntax=docker/dockerfile:1

# --- Stage 1: build the SPA ---------------------------------------------------
# Pinned to the build host's platform: Vite output is platform-independent
# static files, so there is no reason to run npm under emulation.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm test && npm run build

# --- Stage 2: Python runtime with cairo/Pango for exports ----------------------
# Debian's Python is used so PyGObject (Pango) and pycairo come from maintained
# distribution packages; application dependencies live in a venv on top.
FROM debian:trixie-slim AS python-base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv \
        python3-gi python3-gi-cairo python3-cairo gir1.2-pango-1.0 \
        fonts-noto-core fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/.cache
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# --- Stage 3: backend checks (lint + tests); built by scripts/check.sh ---------
FROM python-base AS test
COPY backend/requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
WORKDIR /app
COPY backend/ ./
RUN ruff check . && ruff format --check . && python -m pytest

# --- Stage 4: runtime ---------------------------------------------------------
FROM python-base AS runtime
WORKDIR /app
COPY backend/famtree ./famtree
COPY --from=frontend /build/dist ./static
RUN printf '#!/bin/sh\nexec python -m famtree.cli "$@"\n' > /usr/local/bin/famtree-admin \
    && chmod 755 /usr/local/bin/famtree-admin \
    && mkdir -p /data && chmod 700 /data

ENV FAMTREE_DATA_DIR=/data \
    FAMTREE_KEY_FILE=/run/secrets/famtree_key \
    FAMTREE_STATIC_DIR=/app/static \
    FAMTREE_LISTEN_PORT=8080 \
    FAMTREE_REQUIRE_DATA_MOUNT=true

# Run as an unprivileged user; compose overrides with the host owner's uid/gid.
USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('FAMTREE_LISTEN_PORT', '8080') + '/api/health/ready', timeout=4)"]

STOPSIGNAL SIGTERM
CMD ["python", "-m", "famtree"]
