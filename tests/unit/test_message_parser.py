import json

import pytest

from parser.message_parser import MessageParser, ParseError
from helpers import valid_telemetry


def test_parses_valid_json_object():
    payload = json.dumps(valid_telemetry()).encode()
    assert MessageParser.parse(payload) == valid_telemetry()


def test_does_not_validate_content():
    # Parsing and validation are separate responsibilities: out-of-range values still parse.
    assert MessageParser.parse(b'{"temperature": 999}') == {"temperature": 999}


def test_accepts_non_ascii_utf8():
    assert MessageParser.parse('{"location": "Café-Ä"}'.encode("utf-8")) == {"location": "Café-Ä"}


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"\xff\xfe", "not valid UTF-8"),
        (b"", "not valid JSON"),
        (b"{not json", "not valid JSON"),
        (b"{'single': 'quotes'}", "not valid JSON"),
        (b"[1, 2, 3]", "must be an object, got list"),
        (b'"a string"', "must be an object, got str"),
        (b"42", "must be an object, got int"),
        (b"null", "must be an object, got NoneType"),
    ],
)
def test_rejects_unparseable_payloads(payload, message):
    with pytest.raises(ParseError, match=message):
        MessageParser.parse(payload)
