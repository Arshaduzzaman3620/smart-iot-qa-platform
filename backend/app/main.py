"""SmartIoT REST API. Run from the repo root:  python -m backend.app.main  (port from API_PORT in .env)"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from database.session import SessionLocal

from . import mqtt_publisher
from .api import alerts, auth, commands, firmware, health, sensors, users
from .bootstrap import ensure_admin
from .security import JWT_SECRET, JWT_SECRET_CONFIGURED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not JWT_SECRET_CONFIGURED:
        logger.warning("JWT_SECRET not set: using a random secret, tokens are invalidated when the API restarts")
    elif len(JWT_SECRET.encode()) < 32:
        # HS256 with a short key can be brute-forced offline from any token (RFC 7518 3.2).
        logger.warning("JWT_SECRET is shorter than 32 bytes: use a longer random value")
    ensure_admin(SessionLocal, os.getenv("ADMIN_USERNAME", "admin"), os.getenv("ADMIN_PASSWORD", ""))
    app.state.publisher = mqtt_publisher.from_env()
    app.state.publisher.start()
    yield
    app.state.publisher.stop()


app = FastAPI(title="SmartIoT Sensor API", version="0.2.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sensors.router)
app.include_router(alerts.router)
app.include_router(commands.router)
app.include_router(firmware.viewer)
app.include_router(firmware.download)


# The interactive API docs load Swagger UI / ReDoc from a CDN, so they get no CSP; everything else is JSON.
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


COMMON_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                  (b"referrer-policy", b"no-referrer")]
# API responses are data, never pages: nothing may load, run or frame them. Per-user data and
# tokens must not be kept by browsers or shared caches.
DATA_HEADERS = [(b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                (b"cache-control", b"no-store")]


class SecurityHeaders:
    """Adds the security headers to every HTTP response. A plain ASGI middleware rather than
    @app.middleware("http"), whose BaseHTTPMiddleware is known to misbehave when clients disconnect."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        extra = COMMON_HEADERS + ([] if scope["path"].startswith(DOCS_PATHS) else DATA_HEADERS)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in extra if h[0] not in present]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ConcurrencyLimit:
    """At most `limit` requests inside the app at once; the rest wait here, holding nothing.

    Without it, a load spike let hundreds of requests in, each holding a DB connection while waiting
    for one of the 40 worker threads (FastAPI hops threads for auth, the endpoint and serialization),
    while the threads waited for connections: requests timed out and throughput collapsed. With the
    limit below the thread and connection counts, admitted requests always have both. A request that
    waits longer than `max_wait` gets 503 + Retry-After instead (docs/testing/performance.md)."""

    def __init__(self, app, limit: int, max_wait: float):
        self.app, self.limit, self.max_wait = app, limit, max_wait
        self._slots, self._loop = None, None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        loop = asyncio.get_running_loop()
        if self._loop is not loop:  # one server runs one loop; tests start several (one per TestClient)
            self._slots, self._loop = asyncio.Semaphore(self.limit), loop
        try:
            await asyncio.wait_for(self._slots.acquire(), self.max_wait)
        except TimeoutError:
            response = JSONResponse({"detail": "Server busy"}, status_code=503, headers={"Retry-After": "1"})
            return await response(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            self._slots.release()


app.add_middleware(ConcurrencyLimit, limit=int(os.getenv("API_MAX_CONCURRENCY", "32")),
                   max_wait=float(os.getenv("API_MAX_WAIT", "10")))
# Added last = outermost: even a "Server busy" answer carries the security headers.
app.add_middleware(SecurityHeaders)


@app.exception_handler(PoolTimeoutError)
async def database_busy(request: Request, exc: PoolTimeoutError):
    # Every pooled connection busy for pool_timeout (5 s): overloaded. Say so at once, rather than a 500.
    logger.warning("Database busy on %s %s: connection pool exhausted", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"detail": "Database busy"}, headers={"Retry-After": "1"})


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError):
    # MySQL down/unreachable: a clean 503 instead of a 500 with a stack trace (and no DB details leaked).
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc.orig)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes each rejected value back ("input"). Never do that for a password:
    # responses end up in browser devtools, proxies and logs.
    errors = []
    for error in exc.errors():
        if "password" in error.get("loc", ()):
            error = {k: v for k, v in error.items() if k != "input"}
        errors.append(error)
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


if __name__ == "__main__":
    import uvicorn

    # database.config has already loaded the repo-root .env by this point.
    # Local only by default; the container sets API_HOST=0.0.0.0 so its published port works.
    uvicorn.run(app, host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "8000")))
