"""Firmware upload, download tokens and starting updates (Phase 15e), with MQTT faked."""

import hashlib
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.security import create_download_token, create_token
from database.models import Firmware, FirmwareUpdate, Sensor
from database.session import SessionLocal

IMAGE = b"\x7fELF fake firmware " * 50


@pytest.fixture(scope="module", autouse=True)
def remove_test_firmware(mysql_available):
    """Firmware uploaded here uses version 0.x.y; deleted (with its updates) after the module."""
    yield
    with SessionLocal() as session, session.begin():
        ids = [f.id for f in session.query(Firmware).filter(Firmware.version.like("0.%"))]
        session.query(FirmwareUpdate).filter(FirmwareUpdate.firmware_id.in_(ids)).delete()
        session.query(Firmware).filter(Firmware.id.in_(ids)).delete()


def new_version() -> str:
    """A version no other test uses: 0.<random>.<random>."""
    n = uuid.uuid4().int
    return f"0.{n % 9999}.{(n // 9999) % 9999}"



def upload(client, headers, content=IMAGE, version=None, **params):
    params = {"version": new_version() if version is None else version, **params}
    return client.post("/firmware", headers={**headers, "Content-Type": "application/octet-stream"},
                       params=params, content=content)


@pytest.fixture
def admin(headers_for):
    return headers_for("ADMIN")


@pytest.fixture
def firmware(client, admin):
    return upload(client, admin).json()


# ---- upload ----------------------------------------------------------------------------------

def test_admin_uploads_and_checksum_is_computed(client, admin):
    version = new_version()
    response = upload(client, admin, version=version, filename="fw.bin")
    assert response.status_code == 201
    body = response.json()
    assert (body["version"], body["filename"], body["size"]) == (version, "fw.bin", len(IMAGE))
    assert body["checksum"] == hashlib.sha256(IMAGE).hexdigest()
    assert body["uploaded_by"] == "test-admin"
    assert "content" not in body
    assert version in [f["version"] for f in client.get("/firmware").json()]


def test_default_filename(client, admin):
    version = new_version()
    assert upload(client, admin, version=version).json()["filename"] == f"firmware-{version}.bin"


@pytest.mark.parametrize("role", ["VIEWER", "OPERATOR"])
def test_only_admin_uploads(client, headers_for, role):
    assert upload(client, headers_for(role)).status_code == 403


def test_duplicate_version_is_409(client, admin, firmware):
    assert upload(client, admin, version=firmware["version"]).status_code == 409


@pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-beta", "12345.0.0", "", "1.0.0; drop table"])
def test_bad_version_is_422(client, admin, version):
    assert upload(client, admin, version=version).status_code == 422


@pytest.mark.parametrize("filename", ["../../etc/passwd", "a b.bin", "x" * 101, "<script>.bin"])
def test_bad_filename_is_422(client, admin, filename):
    assert upload(client, admin, filename=filename).status_code == 422


def test_empty_image_is_422(client, admin):
    assert upload(client, admin, content=b"").status_code == 422


def test_size_limit_is_exactly_1_mib(client, admin):
    assert upload(client, admin, content=b"x" * (1024 * 1024)).status_code == 201
    response = upload(client, admin, content=b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413


# ---- download --------------------------------------------------------------------------------

def test_download_with_token_returns_the_exact_bytes(anon_client, firmware):
    token = create_download_token(firmware["id"], "SENSOR-X")
    response = anon_client.get(f"/firmware/{firmware['id']}/download", params={"token": token})
    assert response.status_code == 200
    assert response.content == IMAGE
    assert response.headers["x-checksum-sha256"] == firmware["checksum"]


def test_download_needs_a_token(anon_client, firmware):
    assert anon_client.get(f"/firmware/{firmware['id']}/download").status_code == 422


@pytest.mark.parametrize("make", [
    lambda fw: "garbage",
    lambda fw: create_token("test-admin", "ADMIN"),                 # a login token is not a download token
    lambda fw: create_download_token(fw + 1, "SENSOR-X"),            # token for another image
    lambda fw: create_download_token(fw, "S", minutes=-1),           # expired
])
def test_download_rejects_wrong_tokens(anon_client, firmware, make):
    response = anon_client.get(f"/firmware/{firmware['id']}/download", params={"token": make(firmware["id"])})
    assert response.status_code == 401


def test_download_token_does_not_open_the_api(anon_client, firmware):
    token = create_download_token(firmware["id"], "test-admin")  # even with a real username as subject
    assert anon_client.get("/sensors", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_download_of_missing_image_is_404(anon_client):
    assert anon_client.get("/firmware/999999/download",
                           params={"token": create_download_token(999999, "S")}).status_code == 404


# ---- starting updates ------------------------------------------------------------------------

def start(client, headers, sensor_id, firmware_id):
    return client.post(f"/sensors/{sensor_id}/firmware-updates", headers=headers, json={"firmware_id": firmware_id})


def test_update_is_recorded_and_published_with_a_working_download_link(client, anon_client, headers_for, broker,
                                                                        seeded_sensor, firmware):
    sid = seeded_sensor["sensor_id"]
    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=sid).update({"firmware_version": "1.0.0"})

    response = start(client, headers_for("OPERATOR"), sid, firmware["id"])
    assert response.status_code == 202
    update = response.json()
    assert (update["status"], update["from_version"], update["version"]) == ("REQUESTED", "1.0.0", firmware["version"])

    (topic, payload), = broker.sent
    assert topic == f"iot/sensors/{sid}/firmware"
    assert payload["update_id"] == update["id"]
    assert (payload["version"], payload["size"], payload["sha256"]) == (firmware["version"], firmware["size"],
                                                                         firmware["checksum"])
    # The link in the message is exactly what the sensor will fetch.
    download = anon_client.get(payload["url"])
    assert download.status_code == 200 and download.content == IMAGE
    token = parse_qs(urlparse(payload["url"]).query)["token"][0]
    assert anon_client.get("/sensors", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    assert client.get(f"/firmware-updates/{update['id']}").json()["status"] == "REQUESTED"
    assert [u["id"] for u in client.get(f"/sensors/{sid}/firmware-updates").json()] == [update["id"]]


def test_viewer_cannot_start_an_update(client, broker, seeded_sensor, firmware):
    assert start(client, {}, seeded_sensor["sensor_id"], firmware["id"]).status_code == 403
    assert broker.sent == []


def test_second_update_while_one_runs_is_409(client, headers_for, broker, seeded_sensor, firmware, admin):
    other = upload(client, admin).json()
    sid, op = seeded_sensor["sensor_id"], headers_for("OPERATOR")
    assert start(client, op, sid, firmware["id"]).status_code == 202
    response = start(client, op, sid, other["id"])
    assert response.status_code == 409
    assert "still in progress" in response.json()["detail"]


def test_update_to_the_running_version_is_409(client, headers_for, broker, seeded_sensor, firmware):
    sid = seeded_sensor["sensor_id"]
    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=sid).update({"firmware_version": firmware["version"]})
    assert start(client, headers_for("OPERATOR"), sid, firmware["id"]).status_code == 409
    assert broker.sent == []


def test_unknown_sensor_or_firmware_is_404(client, headers_for, broker, seeded_sensor, firmware):
    op = headers_for("OPERATOR")
    assert start(client, op, "TEST-NOPE", firmware["id"]).status_code == 404
    assert start(client, op, seeded_sensor["sensor_id"], 999999999).status_code == 404


@pytest.mark.parametrize("body", [{}, {"firmware_id": 0}, {"firmware_id": "1"}, {"firmware_id": 1, "force": True}])
def test_invalid_update_body_is_422(client, headers_for, seeded_sensor, body):
    response = client.post(f"/sensors/{seeded_sensor['sensor_id']}/firmware-updates", headers=headers_for("OPERATOR"),
                           json=body)
    assert response.status_code == 422


def test_broker_down_is_503_and_recorded_failed(client, headers_for, broker, seeded_sensor, firmware):
    broker.up = False
    sid = seeded_sensor["sensor_id"]
    assert start(client, headers_for("OPERATOR"), sid, firmware["id"]).status_code == 503
    (update,) = client.get(f"/sensors/{sid}/firmware-updates").json()
    assert (update["status"], update["error_message"]) == ("FAILED", "MQTT broker unreachable")
    # A failed attempt doesn't block the next one.
    broker.up = True
    assert start(client, headers_for("OPERATOR"), sid, firmware["id"]).status_code == 202


def test_unknown_update_id_is_404(client):
    assert client.get("/firmware-updates/999999999").status_code == 404
