import logging
import signal
import sys
import threading
import time
from pathlib import Path

# The shared `database` package lives at the repo root, next to receiver/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import SQLAlchemyError

from config import settings
from mqtt.mqtt_client import MQTTSubscriber
from parser.message_parser import MessageParser, ParseError
from storage.batch_writer import BatchWriter
from storage.command_repository import CommandRepository
from storage.firmware_repository import FirmwareRepository
from storage.offline_detector import OfflineDetector
from storage.telemetry_repository import TelemetryRepository
from validator.device_message_validator import validate_firmware_status, validate_response, validate_status
from validator.telemetry_validator import TelemetryValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("receiver")
alert_logger = logging.getLogger("receiver.alerts")

TELEMETRY_TOPIC = f"{settings.TOPIC_ROOT}/+/telemetry"
# Phase 15d: sensors answer commands on .../response and describe themselves on .../status.
RESPONSE_TOPIC = f"{settings.TOPIC_ROOT}/+/response"
STATUS_TOPIC = f"{settings.TOPIC_ROOT}/+/status"
FIRMWARE_STATUS_TOPIC = f"{settings.TOPIC_ROOT}/+/firmware_status"  # Phase 15e: firmware update progress
TOPICS = [TELEMETRY_TOPIC, RESPONSE_TOPIC, STATUS_TOPIC, FIRMWARE_STATUS_TOPIC]

# Set by Ctrl+C / SIGTERM (e.g. `docker stop`) / Ctrl+Break on Windows. Stopping disconnects from
# the broker first, then lets the writer store every message it already accepted.
stop_requested = threading.Event()


def request_stop(signum, frame):
    logger.info("Stop requested (%s)", signal.Signals(signum).name)
    stop_requested.set()


def install_stop_handlers():
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK exists only on Windows
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)


def log_saved(data: dict, result):
    if result.duplicate:
        logger.warning("Duplicate telemetry from %s ignored (same as id=%s): %s", data["sensor_id"],
                       result.telemetry_id, data)
        return
    logger.info("Stored telemetry id=%s from %s: %s", result.telemetry_id, data["sensor_id"], data)
    for change in result.alert_changes:
        if change.action == "RESOLVE":
            alert_logger.info("Alert resolved for %s: %s", data["sensor_id"], change.alert_type)
        else:
            alert_logger.warning("Alert %s for %s: %s %s - %s",
                                 "raised" if change.action == "RAISE" else "escalated", data["sensor_id"],
                                 change.alert_type, change.severity, change.message)


def log_failed(data: dict, exc: Exception):
    # DB down or rejecting the write: drop this message but keep the receiver running.
    logger.error("Failed to store telemetry from %s: %s", data["sensor_id"], getattr(exc, "orig", exc))


writer = BatchWriter(TelemetryRepository(), log_saved, log_failed, max_batch=settings.RECEIVER_BATCH_MAX)
mqtt_client = MQTTSubscriber(settings.MQTT_HOST, settings.MQTT_PORT, client_id=settings.RECEIVER_CLIENT_ID)
commands = CommandRepository()
firmware = FirmwareRepository()


def topic_sensor_id(topic: str) -> str:
    """iot/sensors/{sensor_id}/telemetry -> sensor_id"""
    return topic.split("/")[2]


def on_message(client, userdata, msg):
    """Every message is acknowledged exactly once: telemetry by the writer once stored (or rejected
    by the database), everything else here once handled. Until then the broker keeps it."""
    if handle_message(msg):
        return  # the writer acknowledges it
    mqtt_client.ack(msg.mid, msg.qos)


def handle_message(msg) -> bool:
    """True if the message was handed to the writer (which acknowledges it later)."""
    if not msg.payload and msg.topic.endswith("/status"):
        return False  # an empty retained message is how a sensor's status is cleared from the broker
    # Receiver never trusts incoming data: parse, validate, and only then store.
    try:
        data = MessageParser.parse(msg.payload)
    except ParseError as exc:
        logger.warning("Rejected message on %s: %s (raw=%r)", msg.topic, exc, msg.payload[:200])
        return False

    kind = msg.topic.rsplit("/", 1)[-1]
    if kind == "response":
        on_response(msg.topic, data)
        return False
    if kind == "status":
        on_status(msg.topic, data)
        return False
    if kind == "firmware_status":
        on_firmware_status(msg.topic, data)
        return False

    errors = TelemetryValidator.validate(data)
    if not errors and data["sensor_id"] != topic_sensor_id(msg.topic):
        # A sensor may only publish its own readings.
        errors.append(f"sensor_id {data['sensor_id']!r} does not match topic {msg.topic!r}")
    if errors:
        logger.warning("Rejected message on %s: %s", msg.topic, "; ".join(errors))
        return False

    # Stored (and logged) by the writer thread, batched with whatever else is waiting.
    writer.submit(data, on_done=lambda: mqtt_client.ack(msg.mid, msg.qos))
    return True


def on_response(topic: str, data: dict):
    """A sensor's answer to a command. Low volume, so stored right here rather than batched."""
    errors = validate_response(data)
    if errors:
        logger.warning("Rejected response on %s: %s", topic, "; ".join(errors))
        return
    sensor_id = topic_sensor_id(topic)
    try:
        applied = commands.complete(sensor_id, data["command_id"], data["status"], data.get("message"))
    except SQLAlchemyError as exc:
        logger.error("Failed to store response from %s: %s", sensor_id, getattr(exc, "orig", exc))
        return
    if applied:
        logger.info("Command %s on %s %s: %s", data["command_id"], sensor_id, data["status"], data.get("message"))
    else:
        # Unknown id, already finished (duplicate, or late after TIMED_OUT), or another sensor's command.
        logger.warning("Ignored response from %s for command %s: no such pending command for this sensor",
                       sensor_id, data["command_id"])


def on_status(topic: str, data: dict):
    errors = validate_status(data)
    if not errors and data.get("sensor_id") not in (None, topic_sensor_id(topic)):
        errors.append(f"sensor_id {data['sensor_id']!r} does not match topic {topic!r}")
    if errors:
        logger.warning("Rejected status on %s: %s", topic, "; ".join(errors))
        return
    sensor_id = topic_sensor_id(topic)
    try:
        commands.save_status(sensor_id, data)
    except SQLAlchemyError as exc:
        logger.error("Failed to store status from %s: %s", sensor_id, getattr(exc, "orig", exc))
        return
    logger.info("Status from %s: firmware %s, %s", sensor_id, data.get("firmware_version"), data.get("name"))


def on_firmware_status(topic: str, data: dict):
    errors = validate_firmware_status(data)
    if errors:
        logger.warning("Rejected firmware status on %s: %s", topic, "; ".join(errors))
        return
    sensor_id = topic_sensor_id(topic)
    try:
        ignored = firmware.progress(sensor_id, data["update_id"], data["status"], data.get("message"))
    except SQLAlchemyError as exc:
        logger.error("Failed to store firmware status from %s: %s", sensor_id, getattr(exc, "orig", exc))
        return
    if ignored:
        logger.warning("Ignored firmware status from %s for update %s: %s", sensor_id, data["update_id"], ignored)
    else:
        log = logger.warning if data["status"] == "FAILED" else logger.info
        log("Firmware update %s on %s: %s %s", data["update_id"], sensor_id, data["status"], data.get("message") or "")


def expire_commands():
    try:
        expired = commands.expire(settings.COMMAND_TIMEOUT)
    except SQLAlchemyError as exc:
        logger.error("Command timeout check failed: %s", getattr(exc, "orig", exc))
        return
    if expired:
        logger.warning("%d command(s) timed out (no response within %g s)", expired, settings.COMMAND_TIMEOUT)
    try:
        expired = firmware.expire(settings.FOTA_TIMEOUT)
    except SQLAlchemyError as exc:
        logger.error("Firmware timeout check failed: %s", getattr(exc, "orig", exc))
        return
    if expired:
        logger.warning("%d firmware update(s) timed out (no progress for %g s)", expired, settings.FOTA_TIMEOUT)


def check_offline(detector: OfflineDetector):
    # During a database outage nothing is stored, so every sensor's last_seen goes stale; and until
    # the held backlog is stored (plus one grace period) the readings proving sensors alive aren't in yet.
    if writer.in_outage or writer.backlog > settings.RECEIVER_BATCH_MAX or (
            writer.outage_ended_at is not None
            and time.monotonic() - writer.outage_ended_at < settings.OFFLINE_STARTUP_GRACE):
        return
    try:
        offline = detector.sweep()
    except SQLAlchemyError as exc:
        logger.error("Offline check failed: %s", getattr(exc, "orig", exc))
        return
    for sensor in offline:
        alert_logger.warning("Sensor %s marked OFFLINE: no telemetry for %.0f s", sensor.sensor_id, sensor.silent_seconds)


def main():
    install_stop_handlers()
    writer.start()
    mqtt_client.set_message_handler(on_message)
    mqtt_client.connect(TOPICS)
    logger.info("Receiver starting, subscribing to %s", ", ".join(TOPICS))

    detector = OfflineDetector(settings.OFFLINE_TIMEOUT)
    next_check = time.monotonic() + settings.OFFLINE_STARTUP_GRACE
    logger.info("Offline detection: timeout %gs, first check in %gs", settings.OFFLINE_TIMEOUT, settings.OFFLINE_STARTUP_GRACE)

    try:
        while not stop_requested.is_set():
            if time.monotonic() >= next_check:
                check_offline(detector)
                expire_commands()
                next_check = time.monotonic() + settings.OFFLINE_CHECK_INTERVAL
            stop_requested.wait(min(1, settings.OFFLINE_CHECK_INTERVAL))
    finally:
        mqtt_client.disconnect()
        # Store what was already accepted before exiting.
        if writer.stop():
            logger.info("Receiver stopped")
        else:
            logger.error("Receiver stopped before storing every queued message")


if __name__ == "__main__":
    main()
