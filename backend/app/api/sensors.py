import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Alert, Sensor, Telemetry, User

from ..deps import get_db, require_role
from ..schemas import AlertOut, SensorOut, SensorUpdateIn, SensorWithLatestOut, TelemetryOut
from .alerts import AlertStatus, alerts_query

logger = logging.getLogger("backend.sensors")
# Reading needs any signed-in user; changes need OPERATOR (per endpoint below).
router = APIRouter(prefix="/sensors", tags=["sensors"], dependencies=[Depends(require_role("VIEWER"))])


def _get_sensor_or_404(db: Session, sensor_id: str) -> Sensor:
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id))
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    return sensor


@router.get("", response_model=list[SensorWithLatestOut])
def list_sensors(db: Session = Depends(get_db)):
    # Each sensor's latest reading via the pointer the receiver maintains: a primary-key join, so
    # the cost depends on the number of sensors, not the size of the telemetry table.
    rows = db.execute(
        select(Sensor, Telemetry)
        .outerjoin(Telemetry, Telemetry.id == Sensor.latest_telemetry_id)
        .order_by(Sensor.sensor_id)
    ).all()
    # Uses ix_alerts_sensor_status: cost follows the number of active alerts, not alert history.
    active_alerts = dict(db.execute(
        select(Alert.sensor_id, func.count()).where(Alert.status == "ACTIVE").group_by(Alert.sensor_id)
    ).all())

    items = []
    for sensor, latest in rows:
        item = SensorWithLatestOut.model_validate(sensor)
        if latest is not None:
            item.latest_telemetry = TelemetryOut.model_validate(latest)
        item.active_alerts = active_alerts.get(sensor.sensor_id, 0)
        items.append(item)
    return items


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: str, db: Session = Depends(get_db)):
    return _get_sensor_or_404(db, sensor_id)


@router.patch("/{sensor_id}", response_model=SensorOut)
def update_sensor(sensor_id: str, body: SensorUpdateIn, db: Session = Depends(get_db),
                  user: User = Depends(require_role("OPERATOR"))):
    sensor = _get_sensor_or_404(db, sensor_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(sensor, field, value)
    db.commit()
    db.refresh(sensor)
    logger.info("Sensor %s updated by %s: %s", sensor_id, user.username, changes)
    return sensor


@router.get("/{sensor_id}/telemetry", response_model=list[TelemetryOut])
def get_sensor_telemetry(
    sensor_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Max rows, newest first"),
    db: Session = Depends(get_db),
):
    # 404 for an unknown sensor, rather than an ambiguous empty list.
    _get_sensor_or_404(db, sensor_id)
    rows = db.scalars(
        select(Telemetry)
        .where(Telemetry.sensor_id == sensor_id)
        .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc())
        .limit(limit)
    ).all()
    return rows


@router.get("/{sensor_id}/alerts", response_model=list[AlertOut])
def get_sensor_alerts(
    sensor_id: str,
    status: AlertStatus | None = Query(None, description="ACTIVE or RESOLVED; omit for both"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows, newest first"),
    db: Session = Depends(get_db),
):
    _get_sensor_or_404(db, sensor_id)
    return db.scalars(alerts_query(status, limit, sensor_id)).all()
