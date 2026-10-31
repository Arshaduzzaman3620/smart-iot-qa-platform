import json
from dataclasses import dataclass, field

# Same limits the API enforces (backend/app/schemas.py). The sensor checks again anyway: anything
# that can publish to its command topic can send it anything.
COMMANDS = ("RESTART", "REQUEST_TELEMETRY", "SET_INTERVAL")
MIN_INTERVAL, MAX_INTERVAL = 1, 3600


class CommandError(ValueError):
    """An unusable command. `command_id` is set when the message had one, so the sensor can still answer."""

    def __init__(self, message: str, command_id: int | None = None):
        super().__init__(message)
        self.command_id = command_id


@dataclass
class Command:
    command_id: int
    name: str
    params: dict = field(default_factory=dict)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_command(payload: bytes) -> Command:
    """Decode and check a command message. No MQTT or sensor state here."""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise CommandError("command must be a JSON object")

    command_id = data.get("command_id")
    if not _is_int(command_id) or command_id < 1:
        raise CommandError("command_id must be a positive integer")
    name, params = data.get("command"), data.get("params", {})
    if name not in COMMANDS:
        raise CommandError(f"unknown command {name!r}", command_id)
    if not isinstance(params, dict):
        raise CommandError("params must be an object", command_id)

    if name == "SET_INTERVAL":
        interval = params.get("interval")
        if not _is_int(interval) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise CommandError(f"interval must be a whole number of seconds, {MIN_INTERVAL}-{MAX_INTERVAL}", command_id)
        params = {"interval": interval}
    elif params:
        raise CommandError(f"{name} takes no params", command_id)
    return Command(command_id, name, params)


def response(command_id: int, ok: bool, message: str) -> str:
    """The message a sensor publishes on iot/sensors/{id}/response."""
    return json.dumps({"command_id": command_id, "status": "SUCCEEDED" if ok else "FAILED", "message": message})
