"""SmartIoT REST API. Run from the repo root:  python -m backend.app.main  (port from API_PORT in .env)"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from database.session import SessionLocal

from . import mqtt_publisher
from .api import alerts, auth, commands, health, sensors, users
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
