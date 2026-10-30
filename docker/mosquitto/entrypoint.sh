#!/bin/sh
# Write the broker's password file from the environment, then start Mosquitto (Phase 15g).
# Passwords never live in the repository; the file is rebuilt on every start, so changing a
# password in .env and restarting the broker is enough.
set -eu
FILE=/mosquitto/data/passwd
rm -f "$FILE"
touch "$FILE"
chmod 0700 "$FILE"
add() {  # user, password
    [ -n "$2" ] && mosquitto_passwd -b "$FILE" "$1" "$2"
}
add sensor "${SENSOR_MQTT_PASSWORD:?SENSOR_MQTT_PASSWORD is required}"
add receiver "${RECEIVER_MQTT_PASSWORD:?RECEIVER_MQTT_PASSWORD is required}"
add api "${API_MQTT_PASSWORD:?API_MQTT_PASSWORD is required}"
add qa "${QA_MQTT_PASSWORD:-}" || true
chown mosquitto:mosquitto "$FILE"
exec /docker-entrypoint.sh mosquitto -c /mosquitto/config/mosquitto.conf
