from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Alert

from ..deps import get_db, require_role
from ..schemas import AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_role("VIEWER"))])

AlertStatus = Literal["ACTIVE", "RESOLVED"]


def alerts_query(status: AlertStatus | None, limit: int, sensor_id: str | None = None):
    query = select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit)
    if status is not None:
        query = query.where(Alert.status == status)
    if sensor_id is not None:
        query = query.where(Alert.sensor_id == sensor_id)
    return query


@router.get("", response_model=list[AlertOut])
def list_alerts(
    status: AlertStatus | None = Query(None, description="ACTIVE or RESOLVED; omit for both"),
    sensor_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000, description="Max rows, newest first"),
    db: Session = Depends(get_db),
):
    return db.scalars(alerts_query(status, limit, sensor_id)).all()
