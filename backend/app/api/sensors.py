from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Sensor, Telemetry

from ..deps import get_db
from ..schemas import SensorOut, TelemetryOut

router = APIRouter(prefix="/sensors", tags=["sensors"])


def _get_sensor_or_404(db: Session, sensor_id: str) -> Sensor:
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id))
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
    return sensor


@router.get("", response_model=list[SensorOut])
def list_sensors(db: Session = Depends(get_db)):
    return db.scalars(select(Sensor).order_by(Sensor.sensor_id)).all()


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
