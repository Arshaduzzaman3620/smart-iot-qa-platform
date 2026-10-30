"""The simulator's fault injection (sensor-simulator/faults, Phase 15f)."""

import json
import random

import pytest

from faults.fault_injector import FaultRates, apply_faults
from parser.message_parser import MessageParser, ParseError
from validator.telemetry_validator import TelemetryValidator

READING = {"sensor_id": "S-1", "timestamp": "2026-10-30T10:00:00Z", "temperature": 21.5, "humidity": 40.0,
           "pressure": 1000.0, "light": 300.0, "battery": 90.0}


def test_no_faults_sends_the_reading_unchanged():
    payloads, faults = apply_faults(READING, FaultRates(), random.Random(1))
    assert faults == [] and [json.loads(p) for p in payloads] == [READING]


def test_invalid_fault_is_rejected_by_the_receivers_validator():
    payloads, faults = apply_faults(READING, FaultRates(invalid=1), random.Random(1))
    assert faults == ["invalid"]
    assert TelemetryValidator.validate(MessageParser.parse(payloads[0]))


def test_malformed_fault_is_rejected_by_the_receivers_parser():
    payloads, faults = apply_faults(READING, FaultRates(malformed=1), random.Random(1))
    assert faults == ["malformed"]
    with pytest.raises(ParseError):
        MessageParser.parse(payloads[0])


def test_duplicate_fault_sends_the_identical_message_twice():
    payloads, faults = apply_faults(READING, FaultRates(duplicate=1), random.Random(1))
    assert faults == ["duplicate"] and len(payloads) == 2 and payloads[0] == payloads[1]
    assert json.loads(payloads[0]) == READING


def test_rates_are_roughly_respected():
    rng, counts = random.Random(42), {"invalid": 0, "malformed": 0, "duplicate": 0}
    for _ in range(2000):
        for fault in apply_faults(READING, FaultRates(0.1, 0.2, 0.3), rng)[1]:
            counts[fault] += 1
    assert 150 < counts["invalid"] < 250
    assert 330 < counts["malformed"] < 470
    assert 520 < counts["duplicate"] < 680


@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_rate_out_of_range_is_refused(rate):
    with pytest.raises(ValueError):
        FaultRates(invalid=rate)
