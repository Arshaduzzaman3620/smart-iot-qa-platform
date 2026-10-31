"""Firmware over the air through every hop with the real simulator (Phase 15e): upload -> API ->
MQTT -> sensor downloads over HTTP with its token, verifies SHA-256, installs, reboots -> progress
-> receiver -> MySQL -> API / dashboard."""

import uuid

import httpx
import pytest
from playwright.sync_api import expect

from browser_servers import API_URL, DASHBOARD_URL
from database.models import Firmware, FirmwareUpdate
from database.session import SessionLocal
from helpers import login_headers, wait_until


@pytest.fixture(scope="module")
def cleanup_firmware():
    yield
    with SessionLocal() as session, session.begin():
        ids = [f.id for f in session.query(Firmware).filter(Firmware.version.like("0.%"))]
        session.query(FirmwareUpdate).filter(FirmwareUpdate.firmware_id.in_(ids)).delete()
        session.query(Firmware).filter(Firmware.id.in_(ids)).delete()


@pytest.fixture
def admin_headers(stack, test_users):
    return login_headers(API_URL, *test_users["ADMIN"])


@pytest.fixture
def image(admin_headers, cleanup_firmware) -> dict:
    version = f"0.{uuid.uuid4().int % 9999}.{uuid.uuid4().int % 9999}"
    response = httpx.post(f"{API_URL}/firmware", params={"version": version}, content=uuid.uuid4().bytes * 64,
                          headers={**admin_headers, "Content-Type": "application/octet-stream"}, timeout=10)
    assert response.status_code == 201, response.text
    return response.json()


def start_update(sensor_id, firmware_id, headers) -> int:
    response = httpx.post(f"{API_URL}/sensors/{sensor_id}/firmware-updates", json={"firmware_id": firmware_id},
                          headers=headers, timeout=10)
    assert response.status_code == 202, response.text
    return response.json()["id"]


def final(update_id, headers) -> dict:
    return wait_until(lambda: (u := httpx.get(f"{API_URL}/firmware-updates/{update_id}", headers=headers).json())
                      ["status"] in ("SUCCEEDED", "FAILED", "TIMED_OUT") and u, timeout=20)


def firmware_of(sensor_id, headers) -> str:
    return httpx.get(f"{API_URL}/sensors/{sensor_id}", headers=headers).json()["firmware_version"]


def test_update_succeeds_and_the_sensor_reports_the_new_version(start_simulator, image, operator_headers):
    sensor_id, log = start_simulator()
    wait_until(lambda: firmware_of(sensor_id, operator_headers) == "1.0.0")

    result = final(start_update(sensor_id, image["id"], operator_headers), operator_headers)
    assert result["status"] == "SUCCEEDED", result
    assert (result["from_version"], result["version"]) == ("1.0.0", image["version"])
    assert firmware_of(sensor_id, operator_headers) == image["version"]
    # It went through every stage, downloaded for real, and rebooted.
    for stage in ("DOWNLOADING", "VERIFYING", "INSTALLING", "SUCCEEDED"):
        assert f": {stage}" in log()
    assert "MQTT client stopped cleanly" in log()


@pytest.mark.parametrize("failure, reason", [
    ("corrupt", "checksum mismatch; staying on 1.0.0"),
    ("install", "install failed (injected); rolled back to 1.0.0"),
    ("download", "download failed: connection reset (injected)"),
])
def test_injected_failure_leaves_the_old_firmware(start_simulator, image, operator_headers, failure, reason):
    sensor_id, _ = start_simulator(FOTA_FAILURE=failure)
    result = final(start_update(sensor_id, image["id"], operator_headers), operator_headers)
    assert (result["status"], result["error_message"]) == ("FAILED", reason)
    assert firmware_of(sensor_id, operator_headers) == "1.0.0"


def test_low_battery_refuses(start_simulator, image, operator_headers):
    sensor_id, _ = start_simulator(FOTA_MIN_BATTERY="101")  # every battery level counts as too low
    result = final(start_update(sensor_id, image["id"], operator_headers), operator_headers)
    assert result["status"] == "FAILED"
    assert result["error_message"].startswith("battery too low")


def test_operator_updates_from_the_dashboard(start_simulator, image, test_users, page):
    sensor_id, _ = start_simulator()
    username, password = test_users["OPERATOR"]
    page.goto(DASHBOARD_URL)
    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()
    page.get_by_test_id(f"sensor-row-{sensor_id}").get_by_test_id("sensor-id").click()

    page.get_by_test_id("fw-select").select_option(label=image["version"])
    page.get_by_test_id("fw-start").click()
    item = page.get_by_test_id("fw-updates").locator("li").first
    expect(item.get_by_test_id("fw-status")).to_have_text("SUCCEEDED", timeout=20_000)
    expect(item.get_by_test_id("fw-versions")).to_have_text(f"1.0.0 → {image['version']}")
    expect(page.get_by_test_id("details-firmware")).to_have_text(image["version"], timeout=10_000)
