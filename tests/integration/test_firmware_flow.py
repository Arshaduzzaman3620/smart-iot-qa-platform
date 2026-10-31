"""The receiver's half of FOTA (Phase 15e): progress reports and timeouts, through the real receiver."""

import uuid
from datetime import timedelta

import pytest

from database.models import Firmware, FirmwareUpdate, Sensor
from database.session import SessionLocal
from helpers import wait_until
from storage.telemetry_repository import utc_now


@pytest.fixture(scope="module")
def image(mysql_available):
    with SessionLocal() as session, session.begin():
        fw = Firmware(version=f"0.{uuid.uuid4().int % 9999}.1", filename="t.bin", checksum="0" * 64, size=1,
                      content=b"x", uploaded_by="test")
        session.add(fw)
        session.flush()
        fw_id, version = fw.id, fw.version
    yield fw_id, version
    with SessionLocal() as session, session.begin():
        session.query(FirmwareUpdate).filter_by(firmware_id=fw_id).delete()
        session.query(Firmware).filter_by(id=fw_id).delete()


@pytest.fixture
def sensor(receiver_process, sensor_id):
    with SessionLocal() as session, session.begin():
        session.add(Sensor(sensor_id=sensor_id, status="ONLINE", firmware_version="1.0.0"))
    return sensor_id


def make_update(sensor_id, firmware_id, status="REQUESTED", idle_seconds=0) -> int:
    when = utc_now() - timedelta(seconds=idle_seconds)
    with SessionLocal() as session, session.begin():
        row = FirmwareUpdate(sensor_id=sensor_id, firmware_id=firmware_id, from_version="1.0.0", status=status,
                             requested_by="test", started_at=when, updated_at=when)
        session.add(row)
        session.flush()
        return row.id


def update_row(update_id) -> FirmwareUpdate:
    with SessionLocal() as session:
        return session.get(FirmwareUpdate, update_id)


def firmware_of(sensor_id) -> str:
    with SessionLocal() as session:
        return session.query(Sensor).filter_by(sensor_id=sensor_id).one().firmware_version


def report(publish, sensor_id, update_id, status, message=None):
    publish(sensor_id, {"update_id": update_id, "status": status, "message": message}, kind="firmware_status")


def test_progress_through_to_success_sets_the_sensors_version(sensor, image, mqtt_publisher):
    fw_id, version = image
    update_id = make_update(sensor, fw_id)
    for status in ("DOWNLOADING", "VERIFYING", "INSTALLING"):
        report(mqtt_publisher, sensor, update_id, status)
        wait_until(lambda: update_row(update_id).status == status)
    assert firmware_of(sensor) == "1.0.0"  # not before it succeeded

    report(mqtt_publisher, sensor, update_id, "SUCCEEDED", "rebooted")
    row = wait_until(lambda: (r := update_row(update_id)).status == "SUCCEEDED" and r)
    assert row.completed_at is not None and row.error_message is None
    assert firmware_of(sensor) == version


def test_failure_keeps_the_old_version_and_the_reason(sensor, image, mqtt_publisher):
    update_id = make_update(sensor, image[0], status="VERIFYING")
    report(mqtt_publisher, sensor, update_id, "FAILED", "checksum mismatch; staying on 1.0.0")
    row = wait_until(lambda: (r := update_row(update_id)).status == "FAILED" and r)
    assert row.error_message == "checksum mismatch; staying on 1.0.0"
    assert firmware_of(sensor) == "1.0.0"


def test_progress_never_goes_backwards(sensor, image, mqtt_publisher, receiver_process):
    update_id = make_update(sensor, image[0], status="INSTALLING")
    report(mqtt_publisher, sensor, update_id, "DOWNLOADING")  # late or replayed
    wait_until(lambda: f"would go back from INSTALLING to DOWNLOADING" in receiver_process())
    assert update_row(update_id).status == "INSTALLING"


def test_finished_update_is_final(sensor, image, mqtt_publisher, receiver_process):
    update_id = make_update(sensor, image[0], status="FAILED")
    report(mqtt_publisher, sensor, update_id, "SUCCEEDED")
    wait_until(lambda: f"update {update_id}: update already FAILED" in receiver_process())
    assert firmware_of(sensor) == "1.0.0"


def test_a_sensor_cannot_report_on_another_sensors_update(sensor, image, mqtt_publisher, receiver_process):
    update_id = make_update(sensor, image[0])
    other = f"{sensor}-X"
    report(mqtt_publisher, other, update_id, "SUCCEEDED")
    wait_until(lambda: f"Ignored firmware status from {other} for update {update_id}" in receiver_process())
    assert update_row(update_id).status == "REQUESTED"


def test_invalid_report_is_rejected(sensor, image, mqtt_publisher, receiver_process):
    update_id = make_update(sensor, image[0])
    report(mqtt_publisher, sensor, update_id, "TIMED_OUT")  # only the receiver may decide that
    wait_until(lambda: f"Rejected firmware status on iot/sensors/{sensor}/firmware_status" in receiver_process())
    assert update_row(update_id).status == "REQUESTED"


def test_stalled_update_times_out(sensor, image):
    # The test receiver runs with FOTA_TIMEOUT=3 (stack_fixtures.py).
    stalled = make_update(sensor, image[0], status="DOWNLOADING", idle_seconds=10)
    row = wait_until(lambda: (r := update_row(stalled)).status == "TIMED_OUT" and r, timeout=10)
    assert row.error_message == "No progress for 3 s"
    assert firmware_of(sensor) == "1.0.0"
