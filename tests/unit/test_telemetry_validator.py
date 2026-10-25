import json
from pathlib import Path

import pytest

from helpers import valid_telemetry
from validator.telemetry_validator import TelemetryValidator

CASES = json.loads((Path(__file__).parents[1] / "test-data" / "telemetry.json").read_text(encoding="utf-8"))


def apply_patch(patch: dict) -> dict:
    data = valid_telemetry()
    for key, value in patch.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


@pytest.mark.parametrize("case", CASES["valid"], ids=lambda c: c["name"])
def test_accepts_valid_telemetry(case):
    assert TelemetryValidator.validate(apply_patch(case["patch"])) == []


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda c: c["name"])
def test_rejects_invalid_telemetry(case):
    errors = TelemetryValidator.validate(apply_patch(case["patch"]))
    assert len(errors) == 1, errors
    assert case["error"] in errors[0]


def test_explicit_null_counts_as_missing():
    errors = TelemetryValidator.validate(valid_telemetry(humidity=None))
    assert errors == ["missing required field: humidity"]


def test_reports_every_missing_field():
    errors = TelemetryValidator.validate({})
    assert len(errors) == 7
    assert all(e.startswith("missing required field") for e in errors)


def test_reports_all_range_errors_at_once():
    errors = TelemetryValidator.validate(valid_telemetry(temperature=200, humidity=-5, battery=101))
    assert len(errors) == 3
