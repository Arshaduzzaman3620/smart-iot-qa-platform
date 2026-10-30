"""Firmware over the air (Phase 15e): upload images, start updates, and serve downloads to sensors.
Flow and failure modes: docs/architecture/fota.md."""

import hashlib
import json
import logging
import re

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, undefer

from database.models import Firmware, FirmwareUpdate, User
from database.session import SessionLocal

from ..deps import get_db, require_role
from ..schemas import VERSION_PATTERN, FirmwareOut, FirmwareUpdateIn, FirmwareUpdateOut
from ..security import DOWNLOAD_SCOPE, create_download_token, decode_token
from .commands import _utc_now, get_publisher
from .sensors import _get_sensor_or_404

logger = logging.getLogger("backend.firmware")

FIRMWARE_MAX_BYTES = 1024 * 1024  # simulated images are tiny; this keeps uploads (and MySQL rows) small
FINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT")
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")

viewer = APIRouter(tags=["firmware"], dependencies=[Depends(require_role("VIEWER"))])
# No user login here: sensors authenticate with the download token from their update message.
download = APIRouter(tags=["firmware"])


# ---- images ----------------------------------------------------------------------------------

def _store_firmware(version: str, filename: str, content: bytes, username: str) -> Firmware:
    with SessionLocal() as db:
        firmware = Firmware(version=version, filename=filename, checksum=hashlib.sha256(content).hexdigest(),
                            size=len(content), content=content, uploaded_by=username)
        db.add(firmware)
        try:
            db.commit()
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Firmware {version} already exists")
        db.refresh(firmware)
        return firmware


@viewer.post("/firmware", response_model=FirmwareOut, status_code=status.HTTP_201_CREATED,
             openapi_extra={"requestBody": {"content": {"application/octet-stream": {}}, "required": True}})
async def upload_firmware(
    request: Request,
    version: str = Query(..., pattern=VERSION_PATTERN, description="e.g. 1.1.0"),
    filename: str | None = Query(None, max_length=100),
    user: User = Depends(require_role("ADMIN")),
):
    """Raw image bytes as the request body (`Content-Type: application/octet-stream`), at most 1 MiB."""
    filename = filename or f"firmware-{version}.bin"
    if not FILENAME_PATTERN.match(filename):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="filename may use A-Z a-z 0-9 _ . - only")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > FIRMWARE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Firmware larger than 1 MiB")
    # Read with a cap, so a missing or false Content-Length can't make the API buffer a huge body.
    content = bytearray()
    async for chunk in request.stream():
        content += chunk
        if len(content) > FIRMWARE_MAX_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Firmware larger than 1 MiB")
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Firmware image is empty")

    firmware = await run_in_threadpool(_store_firmware, version, filename, bytes(content), user.username)
    logger.info("Firmware %s uploaded by %s (%d bytes, sha256 %s)", version, user.username, firmware.size,
                firmware.checksum)
    return firmware


@viewer.get("/firmware", response_model=list[FirmwareOut])
def list_firmware(db: Session = Depends(get_db)):
    return db.scalars(select(Firmware).order_by(Firmware.created_at.desc(), Firmware.id.desc())).all()


@download.get("/firmware/{firmware_id}/download", response_class=Response,
              responses={200: {"content": {"application/octet-stream": {}}}})
def download_firmware(firmware_id: int, token: str = Query(..., max_length=2048), db: Session = Depends(get_db)):
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Download token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid download token")
    # A login token, or a token for a different image, must not work here.
    if claims.get("scope") != DOWNLOAD_SCOPE or claims.get("fw") != firmware_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid download token")
    firmware = db.scalar(select(Firmware).options(undefer(Firmware.content)).where(Firmware.id == firmware_id))
    if firmware is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Firmware {firmware_id} not found")
    logger.info("Firmware %s downloaded by %s", firmware.version, claims["sub"])
    return Response(firmware.content, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{firmware.filename}"',
                             "X-Checksum-SHA256": firmware.checksum})


# ---- updates ---------------------------------------------------------------------------------

@viewer.post("/sensors/{sensor_id}/firmware-updates", response_model=FirmwareUpdateOut,
             status_code=status.HTTP_202_ACCEPTED,
             responses={409: {"description": "Already on that version, or an update is in progress"},
                        503: {"description": "Broker unreachable; recorded as FAILED"}})
def start_update(sensor_id: str, body: FirmwareUpdateIn, db: Session = Depends(get_db),
                 user: User = Depends(require_role("OPERATOR")), publisher=Depends(get_publisher)):
    sensor = _get_sensor_or_404(db, sensor_id)
    firmware = db.get(Firmware, body.firmware_id)
    if firmware is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Firmware {body.firmware_id} not found")
    if sensor.firmware_version == firmware.version:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"{sensor_id} already runs {firmware.version}")
    running = db.scalar(select(FirmwareUpdate).where(FirmwareUpdate.sensor_id == sensor_id,
                                                     FirmwareUpdate.status.not_in(FINAL_STATUSES)))
    if running is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Update {running.id} is still in progress")

    update = FirmwareUpdate(sensor_id=sensor_id, firmware_id=firmware.id, from_version=sensor.firmware_version,
                            status="REQUESTED", requested_by=user.username)
    db.add(update)
    db.commit()
    db.refresh(update)

    payload = {"update_id": update.id, "version": firmware.version, "size": firmware.size,
               "sha256": firmware.checksum,
               "url": f"/firmware/{firmware.id}/download?token={create_download_token(firmware.id, sensor_id)}"}
    if not publisher.publish(f"iot/sensors/{sensor_id}/firmware", json.dumps(payload)):
        update.status, update.error_message, update.completed_at = "FAILED", "MQTT broker unreachable", _utc_now()
        db.commit()
        logger.error("Firmware update %s for %s not sent: broker unreachable", update.id, sensor_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="MQTT broker unreachable")

    logger.info("Firmware update %s: %s %s -> %s, by %s", update.id, sensor_id, sensor.firmware_version,
                firmware.version, user.username)
    return update


@viewer.get("/sensors/{sensor_id}/firmware-updates", response_model=list[FirmwareUpdateOut])
def list_updates(sensor_id: str, limit: int = Query(20, ge=1, le=1000), db: Session = Depends(get_db)):
    _get_sensor_or_404(db, sensor_id)
    return db.scalars(
        select(FirmwareUpdate).where(FirmwareUpdate.sensor_id == sensor_id)
        .order_by(FirmwareUpdate.started_at.desc(), FirmwareUpdate.id.desc()).limit(limit)
    ).all()


@viewer.get("/firmware-updates/{update_id}", response_model=FirmwareUpdateOut)
def get_update(update_id: int, db: Session = Depends(get_db)):
    update = db.get(FirmwareUpdate, update_id)
    if update is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Firmware update {update_id} not found")
    return update
