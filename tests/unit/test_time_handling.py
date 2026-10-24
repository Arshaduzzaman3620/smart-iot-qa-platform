from datetime import datetime, timezone

import pytest

from backend.app.schemas import TelemetryOut
from storage.telemetry_repository import _to_utc_naive


@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("2026-10-24T12:00:00Z", datetime(2026, 10, 24, 12, 0, 0)),
        ("2026-10-24T21:00:00+09:00", datetime(2026, 10, 24, 12, 0, 0)),
        ("2026-10-24T07:00:00-05:00", datetime(2026, 10, 24, 12, 0, 0)),
        ("2026-10-24T12:00:00", datetime(2026, 10, 24, 12, 0, 0)),  # naive taken as UTC
        ("2026-10-25T01:30:00+14:00", datetime(2026, 10, 24, 11, 30, 0)),  # crosses midnight
    ],
)
def test_receiver_stores_timestamps_as_naive_utc(timestamp, expected):
    result = _to_utc_naive(timestamp)
    assert result == expected
    assert result.tzinfo is None


def test_api_labels_naive_db_datetimes_as_utc():
    row = TelemetryOut(
        id=1, sensor_id="S", timestamp=datetime(2026, 10, 24, 12, 0, 0),
        temperature=1, humidity=1, pressure=400, light=1, battery=1,
        received_at=datetime(2026, 10, 24, 12, 0, 1),
    )
    body = row.model_dump(mode="json")
    assert body["timestamp"] == "2026-10-24T12:00:00Z"
    assert body["received_at"] == "2026-10-24T12:00:01Z"


def test_api_keeps_aware_datetimes_unchanged():
    aware = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)
    row = TelemetryOut(id=1, sensor_id="S", timestamp=aware, temperature=1, humidity=1,
                       pressure=400, light=1, battery=1, received_at=aware)
    assert row.timestamp == aware
