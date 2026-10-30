"""Command responses and status announcements from sensors (Phase 15d). No parsing/MQTT/DB logic here."""

RESPONSE_STATUSES = ("SUCCEEDED", "FAILED")
MESSAGE_MAX_LENGTH = 255  # commands.message is VARCHAR(255)
# Column sizes in the sensors table: longer values would be rejected by MySQL.
STATUS_TEXT_FIELDS = {"sensor_type": 50, "name": 100, "location": 100, "firmware_version": 20}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_response(data: dict) -> list[str]:
    """iot/sensors/{id}/response: {"command_id": 12, "status": "SUCCEEDED", "message": "..."}."""
    errors = []
    if not _is_int(data.get("command_id")) or data["command_id"] < 1:
        errors.append("command_id must be a positive integer")
    if data.get("status") not in RESPONSE_STATUSES:
        errors.append(f"status must be one of {', '.join(RESPONSE_STATUSES)}")
    message = data.get("message")
    if message is not None and not isinstance(message, str):
        errors.append("message must be a string")
    return errors


def validate_status(data: dict) -> list[str]:
    """iot/sensors/{id}/status: what a sensor says about itself when it connects."""
    errors = []
    for field, max_length in STATUS_TEXT_FIELDS.items():
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{field} must be a string")
        elif len(value) > max_length:
            errors.append(f"{field} longer than {max_length} characters")
    return errors
