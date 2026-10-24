"""Builders for mocked /api/sensors responses."""


def sensor(sensor_id="SENSOR-001", status="ONLINE", battery=91.87, temperature=22.46, humidity=48.04,
           last_seen="2026-10-24T12:00:00Z", latest=True):
    return {
        "sensor_id": sensor_id, "sensor_type": "ENVIRONMENT", "name": None, "location": None,
        "status": status, "firmware_version": None, "battery": battery, "last_seen": last_seen,
        "created_at": "2026-10-24T11:00:00Z", "updated_at": last_seen or "2026-10-24T11:00:00Z",
        "latest_telemetry": {
            "id": 1, "sensor_id": sensor_id, "timestamp": last_seen, "temperature": temperature,
            "humidity": humidity, "pressure": 1013.0, "light": 400.0, "battery": battery,
            "received_at": last_seen,
        } if latest else None,
    }
