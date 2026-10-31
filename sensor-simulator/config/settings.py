import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", "5"))
SENSOR_COUNT = int(os.getenv("SENSOR_COUNT", "1"))
# Sensor IDs are {prefix}001, {prefix}002, ... Tests use their own prefix so they never collide with real sensors.
SENSOR_ID_PREFIX = os.getenv("SENSOR_ID_PREFIX", "SENSOR-")
# How long a RESTART command keeps a sensor offline, like a device rebooting.
RESTART_SECONDS = float(os.getenv("RESTART_SECONDS", "3"))
