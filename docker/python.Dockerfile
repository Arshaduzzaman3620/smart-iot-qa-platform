# One image for every Python service (receiver, API, simulator, init-db), plus a `tests` target
# that adds the test dependencies, Chromium and Node. Built from the repo root by compose.yaml.

# --- app: the services -----------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS app

# PIP_DEFAULT_TIMEOUT / PIP_RETRIES: on a slow or flaky network a truncated download otherwise
# fails the build with "THESE PACKAGES DO NOT MATCH THE HASHES" (seen 2026-10-30).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=5

WORKDIR /app

# Requirements first, so code changes don't reinstall dependencies.
# Folder layout is kept because the files include each other (-r ../database/requirements.txt).
COPY database/requirements.txt database/
COPY backend/requirements.txt backend/
COPY receiver/requirements.txt receiver/
COPY sensor-simulator/requirements.txt sensor-simulator/
RUN pip install -r backend/requirements.txt -r receiver/requirements.txt -r sensor-simulator/requirements.txt

COPY database database
COPY backend backend
COPY receiver receiver
COPY sensor-simulator sensor-simulator

RUN useradd --create-home --uid 10001 app
USER app

# --- tests: the whole suite, run by compose.test.yaml ----------------------------------------
FROM app AS tests

USER root

# Node for the Vite dev server the browser tests start. Copied from the official image so the
# version is pinned and no package repository is needed.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Playwright's own Chromium (matches the pinned playwright version, works on amd64 and arm64).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY tests/requirements.txt tests/
COPY qa-assistant/requirements.txt qa-assistant/
RUN pip install -r tests/requirements.txt && playwright install --with-deps chromium

# Linux node_modules built inside the image, never the host's (esbuild ships per-OS binaries).
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund

COPY . .

CMD ["pytest"]
