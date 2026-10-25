"""SmartIoT REST API. Run from the repo root:  python -m backend.app.main  (port from API_PORT in .env)"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from .api import alerts, health, sensors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backend")

app = FastAPI(title="SmartIoT Sensor API", version="0.1.0")
app.include_router(health.router)
app.include_router(sensors.router)
app.include_router(alerts.router)


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError):
    # MySQL down/unreachable: a clean 503 instead of a 500 with a stack trace (and no DB details leaked).
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc.orig)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


if __name__ == "__main__":
    import uvicorn

    # database.config has already loaded the repo-root .env by this point.
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("API_PORT", "8000")))
