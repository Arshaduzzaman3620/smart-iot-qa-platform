import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
# The broker keeps a persistent session per client ID, so it must be stable and unique per receiver.
RECEIVER_CLIENT_ID = os.getenv("RECEIVER_CLIENT_ID", "receiver")
# Two-level topic root: {TOPIC_ROOT}/{sensor_id}/telemetry. Only changed by reliability tests, which
# need their own namespace next to a running receiver.
TOPIC_ROOT = os.getenv("TOPIC_ROOT", "iot/sensors")

# Offline detection: a sensor with no stored reading for OFFLINE_TIMEOUT seconds is marked OFFLINE.
# Default 30 s = 6 missed readings at the default 5 s interval, so a short hiccup isn't an outage.
OFFLINE_TIMEOUT = float(os.getenv("OFFLINE_TIMEOUT", "30"))
OFFLINE_CHECK_INTERVAL = float(os.getenv("OFFLINE_CHECK_INTERVAL", "5"))
# Right after the receiver (re)starts, last_seen is stale for every sensor because nothing was
# stored while it was down. Wait this long before the first check so live sensors can report in.
OFFLINE_STARTUP_GRACE = float(os.getenv("OFFLINE_STARTUP_GRACE", str(OFFLINE_TIMEOUT)))

# Most messages a single transaction stores when they queue up under load (one commit for all).
RECEIVER_BATCH_MAX = int(os.getenv("RECEIVER_BATCH_MAX", "200"))

# A command still unanswered after this many seconds becomes TIMED_OUT (checked with the offline check).
COMMAND_TIMEOUT = float(os.getenv("COMMAND_TIMEOUT", "30"))
# A firmware update with no progress report for this many seconds becomes TIMED_OUT.
FOTA_TIMEOUT = float(os.getenv("FOTA_TIMEOUT", "300"))
