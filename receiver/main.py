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
from storage.offline_detector import OfflineDetector
from storage.telemetry_repository import TelemetryRepository
from validator.telemetry_validator import TelemetryValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("receiver")
alert_logger = logging.getLogger("receiver.alerts")

TELEMETRY_TOPIC = "iot/sensors/+/telemetry"

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


def topic_sensor_id(topic: str) -> str:
    """iot/sensors/{sensor_id}/telemetry -> sensor_id"""
    return topic.split("/")[2]


def on_message(client, userdata, msg):
    # Receiver never trusts incoming data: parse, validate, and only then store.
    try:
        data = MessageParser.parse(msg.payload)
    except ParseError as exc:
        logger.warning("Rejected message on %s: %s (raw=%r)", msg.topic, exc, msg.payload[:200])
        return

    errors = TelemetryValidator.validate(data)
    if not errors and data["sensor_id"] != topic_sensor_id(msg.topic):
        # A sensor may only publish its own readings.
        errors.append(f"sensor_id {data['sensor_id']!r} does not match topic {msg.topic!r}")
    if errors:
        logger.warning("Rejected message on %s: %s", msg.topic, "; ".join(errors))
        return

    # Stored (and logged) by the writer thread, batched with whatever else is waiting.
    writer.submit(data)


def check_offline(detector: OfflineDetector):
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
    mqtt_client = MQTTSubscriber(settings.MQTT_HOST, settings.MQTT_PORT, client_id="receiver")
    mqtt_client.set_message_handler(on_message)
    mqtt_client.connect([TELEMETRY_TOPIC])
    logger.info("Receiver starting, subscribing to %s", TELEMETRY_TOPIC)

    detector = OfflineDetector(settings.OFFLINE_TIMEOUT)
    next_check = time.monotonic() + settings.OFFLINE_STARTUP_GRACE
    logger.info("Offline detection: timeout %gs, first check in %gs", settings.OFFLINE_TIMEOUT, settings.OFFLINE_STARTUP_GRACE)

    try:
        while not stop_requested.is_set():
            if time.monotonic() >= next_check:
                check_offline(detector)
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
