import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Command, User

from ..deps import get_db, require_role
from ..schemas import CommandIn, CommandOut
from .sensors import _get_sensor_or_404

logger = logging.getLogger("backend.commands")
router = APIRouter(tags=["commands"], dependencies=[Depends(require_role("VIEWER"))])


def get_publisher(request: Request):
    """The app's MQTT publisher (started in main.lifespan). Overridden in tests."""
    return request.app.state.publisher


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


@router.post("/sensors/{sensor_id}/commands", response_model=CommandOut, status_code=status.HTTP_202_ACCEPTED,
             responses={503: {"description": "Broker unreachable; the command is recorded as FAILED"}})
def send_command(sensor_id: str, body: CommandIn, db: Session = Depends(get_db),
                 user: User = Depends(require_role("OPERATOR")), publisher=Depends(get_publisher)):
    """Publish a command to the sensor. 202: sent, not yet done -- poll the command for its outcome."""
    _get_sensor_or_404(db, sensor_id)
    params = body.params()
    # Stored first so the sensor's response (which can arrive within milliseconds) finds its row.
    command = Command(sensor_id=sensor_id, command=body.command, params=json.dumps(params), status="SENT",
                      requested_by=user.username)
    db.add(command)
    db.commit()
    db.refresh(command)  # created_at comes from MySQL

    payload = {"command_id": command.id, "command": body.command, "params": params,
               "issued_at": command.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if not publisher.publish(f"iot/sensors/{sensor_id}/command", json.dumps(payload)):
        command.status, command.message, command.completed_at = "FAILED", "MQTT broker unreachable", _utc_now()
        db.commit()
        logger.error("Command %s %s for %s not sent: broker unreachable", command.id, body.command, sensor_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="MQTT broker unreachable")

    logger.info("Command %s %s%s sent to %s by %s", command.id, body.command, params or "", sensor_id, user.username)
    return command


@router.get("/sensors/{sensor_id}/commands", response_model=list[CommandOut])
def list_commands(sensor_id: str, limit: int = Query(20, ge=1, le=1000), db: Session = Depends(get_db)):
    _get_sensor_or_404(db, sensor_id)
    return db.scalars(
        select(Command).where(Command.sensor_id == sensor_id)
        .order_by(Command.created_at.desc(), Command.id.desc()).limit(limit)
    ).all()


@router.get("/commands/{command_id}", response_model=CommandOut)
def get_command(command_id: int, db: Session = Depends(get_db)):
    command = db.get(Command, command_id)
    if command is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Command {command_id} not found")
    return command
