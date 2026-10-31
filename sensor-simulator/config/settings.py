import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
# Broker account for devices (docker/mosquitto/acl). Default = the Compose dev password.
MQTT_USERNAME = "sensor"
MQTT_PASSWORD = os.getenv("SENSOR_MQTT_PASSWORD", "sensor-dev-password")
# Two-level topic root: {TOPIC_ROOT}/{sensor_id}/telemetry. Only changed by reliability tests.
TOPIC_ROOT = os.getenv("TOPIC_ROOT", "iot/sensors")
SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", "5"))
SENSOR_COUNT = int(os.getenv("SENSOR_COUNT", "1"))
# Sensor IDs are {prefix}001, {prefix}002, ... Tests use their own prefix so they never collide with real sensors.
SENSOR_ID_PREFIX = os.getenv("SENSOR_ID_PREFIX", "SENSOR-")
# How long a RESTART command keeps a sensor offline, like a device rebooting.
RESTART_SECONDS = float(os.getenv("RESTART_SECONDS", "3"))

# Firmware over the air (docs/architecture/fota.md).
API_BASE_URL = os.getenv("API_BASE_URL", f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}")
# Inject a failure into every update: none, download, corrupt (checksum mismatch), install (rolls back).
FOTA_FAILURE = os.getenv("FOTA_FAILURE", "none")
# Below this battery level a sensor refuses to update, like real devices do.
FOTA_MIN_BATTERY = float(os.getenv("FOTA_MIN_BATTERY", "20"))
# Simulated time each stage takes, so progress is visible on the dashboard.
FOTA_STEP_SECONDS = float(os.getenv("FOTA_STEP_SECONDS", "1"))

# Reliability (docs/testing/reliability.md). Readings taken while the broker is unreachable are kept,
# up to this many per sensor (oldest dropped first), and sent in order once it is back.
SENSOR_BUFFER_MAX = int(os.getenv("SENSOR_BUFFER_MAX", "1000"))
# Fault injection: probability per reading, 0-1.
FAULT_INVALID_RATE = float(os.getenv("FAULT_INVALID_RATE", "0"))
FAULT_MALFORMED_RATE = float(os.getenv("FAULT_MALFORMED_RATE", "0"))
FAULT_DUPLICATE_RATE = float(os.getenv("FAULT_DUPLICATE_RATE", "0"))
