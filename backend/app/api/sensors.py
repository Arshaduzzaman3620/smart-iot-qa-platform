from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Sensor, Telemetry

from ..deps import get_db
from ..schemas import SensorOut, SensorWithLatestOut, TelemetryOut

router = APIRouter(prefix="/sensors", tags=["sensors"])


def _get_sensor_or_404(db: Session, sensor_id: str) -> Sensor:
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id))
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    return sensor


@router.get("", response_model=list[SensorWithLatestOut])
def list_sensors(db: Session = Depends(get_db)):
    sensors = db.scalars(select(Sensor).order_by(Sensor.sensor_id)).all()

    # Latest reading per sensor in one query (highest id = most recently stored), instead of
    # one query per sensor -- the dashboard polls this endpoint for every sensor at once.
    latest_ids = select(func.max(Telemetry.id)).group_by(Telemetry.sensor_id)
    latest = {t.sensor_id: t for t in db.scalars(select(Telemetry).where(Telemetry.id.in_(latest_ids)))}

    items = []
    for sensor in sensors:
        item = SensorWithLatestOut.model_validate(sensor)
        if sensor.sensor_id in latest:
            item.latest_telemetry = TelemetryOut.model_validate(latest[sensor.sensor_id])
        items.append(item)
    return items


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: str, db: Session = Depends(get_db)):
    return _get_sensor_or_404(db, sensor_id)


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
