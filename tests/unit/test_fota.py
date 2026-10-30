"""Firmware over the air (Phase 15e): the device side (sensor-simulator/fota), the receiver's checks on
progress reports, and download tokens."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.app.security import DOWNLOAD_SCOPE, create_download_token, create_token, decode_token
from fota.fota_client import FotaError, UpdateRequest, parse_update, run_update, verify
from validator.device_message_validator import validate_firmware_status

IMAGE = b"firmware-image-" * 100
SHA = hashlib.sha256(IMAGE).hexdigest()


def message(**overrides) -> bytes:
    data = {"update_id": 5, "version": "1.1.0", "size": len(IMAGE), "sha256": SHA,
            "url": "/firmware/2/download?token=abc"}
    data.update(overrides)
    return json.dumps(data).encode()


def request(**overrides) -> UpdateRequest:
    return parse_update(message(**overrides))


# ---- parse_update ----------------------------------------------------------------------------

def test_valid_update_request():
    r = request()
    assert (r.update_id, r.version, r.size, r.sha256) == (5, "1.1.0", len(IMAGE), SHA)


@pytest.mark.parametrize("field, value", [
    ("version", "v1.1"), ("version", "1.1"), ("version", 110), ("version", "1.1.0; rm -rf /"),
    ("size", 0), ("size", 1024 * 1024 + 1), ("size", "100"), ("size", True),
    ("sha256", "abc"), ("sha256", SHA.upper()), ("sha256", None),
    ("url", "http://evil.example/fw.bin"), ("url", "//evil.example/fw"), ("url", "/users"), ("url", None),
])
def test_invalid_field_is_rejected_with_the_update_id(field, value):
    with pytest.raises(FotaError) as exc:
        request(**{field: value})
    assert exc.value.update_id == 5  # so the sensor can report FAILED


@pytest.mark.parametrize("payload", [b"", b"nope", b"[]", json.dumps({"update_id": "5"}).encode(),
                                     json.dumps({"update_id": 0}).encode()])
def test_unusable_message_has_no_id(payload):
    with pytest.raises(FotaError) as exc:
        parse_update(payload)
    assert exc.value.update_id is None


# ---- verify / run_update ---------------------------------------------------------------------

def test_verify():
    r = request()
    assert verify(IMAGE, r) is None
    assert verify(IMAGE[:-1], r).startswith("size mismatch")
    assert verify(IMAGE[:-1] + b"X", r) == "checksum mismatch"


def update(failure="none", battery=80.0, current="1.0.0", fetch=None, **overrides):
    reports = []
    version = run_update(request(**overrides), current, battery, lambda s, m: reports.append(s),
                         base_url="http://api", failure=failure, step_seconds=0,
                         fetch=fetch or (lambda base, path: IMAGE))
    return version, reports


def test_successful_update_reports_each_stage_in_order():
    version, reports = update()
    assert version == "1.1.0"
    assert reports == ["DOWNLOADING", "VERIFYING", "INSTALLING"]


def test_download_uses_the_api_base_and_the_path_from_the_message():
    seen = []
    update(fetch=lambda base, path: seen.append((base, path)) or IMAGE)
    assert seen == [("http://api", "/firmware/2/download?token=abc")]


@pytest.mark.parametrize("failure, stage, reason", [
    ("download", ["DOWNLOADING"], "download failed"),
    ("corrupt", ["DOWNLOADING", "VERIFYING"], "checksum mismatch; staying on 1.0.0"),
    ("install", ["DOWNLOADING", "VERIFYING", "INSTALLING"], "rolled back to 1.0.0"),
])
def test_injected_failures_stop_at_the_right_stage(failure, stage, reason):
    reports = []
    with pytest.raises(FotaError, match=reason) as exc:
        run_update(request(), "1.0.0", 80, lambda s, m: reports.append(s), base_url="x", failure=failure,
                   step_seconds=0, fetch=lambda b, p: IMAGE)
    assert reports == stage
    assert exc.value.update_id == 5


def test_real_download_error_is_a_failure_not_a_crash():
    def broken(base, path):
        raise FotaError("download failed: HTTP 401")

    with pytest.raises(FotaError, match="HTTP 401") as exc:
        update(fetch=broken)
    assert exc.value.update_id == 5


def test_tampered_image_from_the_server_is_caught():
    with pytest.raises(FotaError, match="checksum mismatch"):
        update(fetch=lambda b, p: IMAGE[:-1] + b"!")


@pytest.mark.parametrize("battery, ok", [(19.9, False), (20.0, True)])
def test_low_battery_refuses_before_downloading(battery, ok):
    if ok:
        assert update(battery=battery)[0] == "1.1.0"
    else:
        with pytest.raises(FotaError, match="battery too low"):
            update(battery=battery)


def test_same_version_is_refused():
    with pytest.raises(FotaError, match="already running 1.1.0"):
        update(current="1.1.0")


# ---- receiver: firmware status reports ---------------------------------------------------------

@pytest.mark.parametrize("status", ["DOWNLOADING", "VERIFYING", "INSTALLING", "SUCCEEDED", "FAILED"])
def test_device_statuses_accepted(status):
    assert validate_firmware_status({"update_id": 1, "status": status}) == []


@pytest.mark.parametrize("data", [
    {"update_id": 1, "status": "TIMED_OUT"}, {"update_id": 1, "status": "REQUESTED"},
    {"update_id": 1, "status": "done"}, {"update_id": 0, "status": "FAILED"},
    {"update_id": "1", "status": "FAILED"}, {"update_id": 1, "status": "FAILED", "message": 3},
])
def test_device_cannot_claim_other_statuses_or_bad_fields(data):
    assert validate_firmware_status(data)


# ---- download tokens -------------------------------------------------------------------------

def test_download_token_names_the_image_and_sensor():
    claims = decode_token(create_download_token(7, "SENSOR-001"))
    assert (claims["sub"], claims["fw"], claims["scope"]) == ("SENSOR-001", 7, DOWNLOAD_SCOPE)


def test_download_token_expires_after_10_minutes():
    old = create_download_token(7, "S", now=datetime.now(timezone.utc) - timedelta(minutes=11))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(old)


def test_login_token_has_no_scope():
    assert "scope" not in decode_token(create_token("alice", "ADMIN"))
