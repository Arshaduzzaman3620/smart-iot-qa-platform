from datetime import datetime, timezone


class Sensor:
    """Holds sensor identity and state. No MQTT or database logic belongs here."""

    def __init__(self, sensor_id: str, sensor_type: str, name: str, location: str,
                 firmware_version: str = "1.0.0", battery: float = 100.0, interval: float = 5):
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.name = name
        self.location = location
        self.firmware_version = firmware_version
        self.battery = battery
        self.status = "OFFLINE"
        self.created_at = datetime.now(timezone.utc)
        self.last_seen = None
        self.interval = interval  # seconds between readings; changed by SET_INTERVAL

    def describe(self) -> dict:
        """What the sensor announces on iot/sensors/{id}/status when it connects."""
        return {"sensor_id": self.sensor_id, "sensor_type": self.sensor_type, "name": self.name,
                "location": self.location, "firmware_version": self.firmware_version, "interval": self.interval}

    def mark_online(self):
        self.status = "ONLINE"

    def mark_offline(self):
        self.status = "OFFLINE"

    def mark_error(self):
        self.status = "ERROR"

    def update_battery(self, battery: float):
        self.battery = battery

    def touch(self):
        self.last_seen = datetime.now(timezone.utc)
