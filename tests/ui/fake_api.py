"""Builders for mocked /api/sensors, /api/alerts and /api/auth/login responses."""


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
        "active_alerts": 0,
    }


def alert(alert_id=1, sensor_id="SENSOR-001", alert_type="LOW_BATTERY", severity="WARNING", value=15.0,
          message="Battery low: 15 % (below 20 %)", created_at="2026-10-24T12:00:00Z"):
    return {
        "id": alert_id, "sensor_id": sensor_id, "alert_type": alert_type, "severity": severity, "value": value,
        "message": message, "status": "ACTIVE", "created_at": created_at, "resolved_at": None,
    }


def fake_session(role: str = "VIEWER", username: str = "ui-tester") -> dict:
    """What the dashboard keeps in sessionStorage after a login (the token is never checked: API is mocked)."""
    return {"access_token": f"fake-token-{role.lower()}", "token_type": "bearer", "expires_in": 3600,
            "user": {"username": username, "role": role, "created_at": "2026-10-24T11:00:00Z"}}
