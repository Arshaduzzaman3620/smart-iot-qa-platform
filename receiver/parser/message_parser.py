import json


class ParseError(Exception):
    """Raised when a raw MQTT payload cannot be parsed into a telemetry dict."""


class MessageParser:
    """Turns a raw MQTT payload into a dict. Decoding/parsing only -- no validation here."""

    @staticmethod
    def parse(raw_payload: bytes) -> dict:
        try:
            text = raw_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"payload is not valid UTF-8: {exc}") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"payload is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ParseError(f"payload JSON must be an object, got {type(data).__name__}")

        return data
