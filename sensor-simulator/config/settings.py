import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", "5"))
SENSOR_COUNT = int(os.getenv("SENSOR_COUNT", "1"))
