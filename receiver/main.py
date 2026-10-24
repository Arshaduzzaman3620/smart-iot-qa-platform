import logging
import sys
import time
from pathlib import Path

# The shared `database` package lives at the repo root, next to receiver/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import SQLAlchemyError

from config import settings
from mqtt.mqtt_client import MQTTSubscriber
from parser.message_parser import MessageParser, ParseError
from storage.telemetry_repository import TelemetryRepository
from validator.telemetry_validator import TelemetryValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("receiver")

TELEMETRY_TOPIC = "iot/sensors/+/telemetry"

repository = TelemetryRepository()


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

    try:
        telemetry_id = repository.save(data)
    except SQLAlchemyError as exc:
        # DB down or rejecting the write: drop this message but keep the receiver running.
        logger.error("Failed to store telemetry from %s: %s", data["sensor_id"], getattr(exc, "orig", exc))
        return

    logger.info("Stored telemetry id=%s from %s: %s", telemetry_id, data["sensor_id"], data)


def main():
    mqtt_client = MQTTSubscriber(settings.MQTT_HOST, settings.MQTT_PORT, client_id="receiver")
    mqtt_client.set_message_handler(on_message)
    mqtt_client.connect([TELEMETRY_TOPIC])
    logger.info("Receiver starting, subscribing to %s", TELEMETRY_TOPIC)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stop requested (Ctrl+C)")
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
