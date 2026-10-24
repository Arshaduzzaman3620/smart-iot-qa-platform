import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..deps import get_db
from ..schemas import HealthOut

logger = logging.getLogger("backend.health")
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check: database unavailable: %s", getattr(exc, "orig", exc))
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})
    return HealthOut(status="ok", database="ok")
