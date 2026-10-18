REQUIRED_FIELDS = ("sensor_id", "timestamp", "temperature", "humidity", "pressure", "light", "battery")

# (min, max) per docs/architecture/sensor-behavior.md "Data ranges" table.
RANGES = {
    "temperature": (-40, 85),
    "humidity": (0, 100),
    "pressure": (300, 1100),
    "light": (0, 100000),
    "battery": (0, 100),
}


class TelemetryValidator:
    """Enforces required fields, types, and value ranges. No parsing/MQTT/DB logic here."""

    @staticmethod
    def validate(data: dict) -> list[str]:
        """Return a list of validation error strings. Empty list means valid."""
        errors = []

        for field in REQUIRED_FIELDS:
            if field not in data or data[field] is None:
                errors.append(f"missing required field: {field}")

        if errors:
            # Range/type checks need the field to be present first.
            return errors

        if not isinstance(data["sensor_id"], str) or not data["sensor_id"]:
            errors.append("sensor_id must be a non-empty string")

        if not isinstance(data["timestamp"], str) or not data["timestamp"]:
            errors.append("timestamp must be a non-empty string")

        for field, (low, high) in RANGES.items():
            value = data[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{field} must be a number, got {type(value).__name__}")
                continue
            if not (low <= value <= high):
                errors.append(f"{field}={value} out of range [{low}, {high}]")

        return errors
