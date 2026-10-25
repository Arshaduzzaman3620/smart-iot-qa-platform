"""Batched writes against real MySQL: one transaction behaves exactly like saving one by one."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database.models import Alert, Sensor, Telemetry
from database.session import SessionLocal
from helpers import valid_telemetry, wait_until
from storage.batch_writer import BatchWriter
from storage.telemetry_repository import TelemetryRepository

pytestmark = pytest.mark.usefixtures("clean_test_rows")

repo = TelemetryRepository()


def reading(sensor_id: str, second: int, **values) -> dict:
    return valid_telemetry(sensor_id, timestamp=f"2026-10-24T12:00:{second:02d}Z", **values)


def telemetry_rows(*sensor_ids: str) -> list[Telemetry]:
    with SessionLocal() as session:
        return session.scalars(
            select(Telemetry).where(Telemetry.sensor_id.in_(sensor_ids)).order_by(Telemetry.id)
        ).all()


def alerts(sensor_id: str) -> list[Alert]:
    with SessionLocal() as session:
        return session.scalars(select(Alert).where(Alert.sensor_id == sensor_id).order_by(Alert.id)).all()


def get_sensor(sensor_id: str) -> Sensor | None:
    with SessionLocal() as session:
        return session.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id))


def test_batch_stores_every_message_with_results_in_order(sensor_id):
    ids = [f"{sensor_id}-{i}" for i in range(3)]
    batch = [reading(sid, second) for second in range(2) for sid in ids]

    results = repo.save_batch(batch)

    assert [r.telemetry_id for r in results] == sorted(r.telemetry_id for r in results)
    rows = telemetry_rows(*ids)
    assert [(r.id, r.sensor_id) for r in rows] == [(res.telemetry_id, d["sensor_id"]) for res, d in zip(results, batch)]
    for sid in ids:
        assert get_sensor(sid).status == "ONLINE"


def test_alerts_within_one_batch_match_one_by_one_processing(sensor_id):
    batch = [reading(sensor_id, 0, battery=15), reading(sensor_id, 1, battery=14),
             reading(sensor_id, 2, battery=8), reading(sensor_id, 3, battery=30)]

    results = repo.save_batch(batch)

    assert [[(c.action, c.alert_type, c.severity) for c in r.alert_changes] for r in results] == [
        [("RAISE", "LOW_BATTERY", "WARNING")],
        [],                                            # continuing breach: no duplicate
        [("ESCALATE", "LOW_BATTERY", "CRITICAL")],
        [("RESOLVE", "LOW_BATTERY", None)],
    ]
    [alert] = alerts(sensor_id)
    assert (alert.severity, alert.status) == ("CRITICAL", "RESOLVED")


def test_out_of_order_readings_in_one_batch_keep_the_newest_as_latest(sensor_id):
    results = repo.save_batch([reading(sensor_id, 5, temperature=11.0), reading(sensor_id, 1, temperature=10.0, battery=5)])

    sensor = get_sensor(sensor_id)
    assert sensor.latest_telemetry_id == results[0].telemetry_id
    assert results[1].alert_changes == []   # the late reading is not judged
    assert alerts(sensor_id) == []


def test_batch_is_all_or_nothing(sensor_id):
    too_long = "TEST-" + "X" * 60  # bypasses the validator, rejected by VARCHAR(50)
    with pytest.raises(SQLAlchemyError):
        repo.save_batch([reading(sensor_id, 0), reading(too_long, 0), reading(sensor_id, 1)])
    assert telemetry_rows(sensor_id) == []
    assert get_sensor(sensor_id) is None


def test_writer_isolates_a_message_the_database_rejects(sensor_id):
    saved, failed = [], []
    writer = BatchWriter(repo, lambda d, r: saved.append(d["timestamp"]), lambda d, e: failed.append(d["sensor_id"]))
    too_long = "TEST-" + "X" * 60
    for message in (reading(sensor_id, 0), reading(too_long, 0), reading(sensor_id, 1)):
        writer.submit(message)
    writer.start()
    assert writer.stop()

    assert failed == [too_long]
    assert saved == ["2026-10-24T12:00:00Z", "2026-10-24T12:00:01Z"]
    assert len(telemetry_rows(sensor_id)) == 2


@pytest.mark.usefixtures("receiver_process")
def test_burst_through_receiver_is_stored_once_in_per_sensor_order(mqtt_publisher, sensor_id):
    ids = [f"{sensor_id}-{i}" for i in range(20)]
    for second in range(15):
        for sid in ids:
            mqtt_publisher(sid, reading(sid, second, temperature=second))

    rows = wait_until(lambda: len(telemetry_rows(*ids)) == 300 and telemetry_rows(*ids), timeout=30)
    for sid in ids:
        mine = [r for r in rows if r.sensor_id == sid]
        assert [r.temperature for r in mine] == list(range(15))  # stored in the order sent
        assert get_sensor(sid).latest_telemetry_id == mine[-1].id
