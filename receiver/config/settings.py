import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Offline detection: a sensor with no stored reading for OFFLINE_TIMEOUT seconds is marked OFFLINE.
# Default 30 s = 6 missed readings at the default 5 s interval, so a short hiccup isn't an outage.
OFFLINE_TIMEOUT = float(os.getenv("OFFLINE_TIMEOUT", "30"))
OFFLINE_CHECK_INTERVAL = float(os.getenv("OFFLINE_CHECK_INTERVAL", "5"))
# Right after the receiver (re)starts, last_seen is stale for every sensor because nothing was
# stored while it was down. Wait this long before the first check so live sensors can report in.
OFFLINE_STARTUP_GRACE = float(os.getenv("OFFLINE_STARTUP_GRACE", str(OFFLINE_TIMEOUT)))
