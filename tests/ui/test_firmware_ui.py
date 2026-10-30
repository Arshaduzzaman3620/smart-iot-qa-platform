"""Firmware library and the sensor's firmware panel (Phase 15e), API mocked."""

import json

from playwright.sync_api import expect

from fake_api import mock_details, sensor


def image(firmware_id=1, version="1.1.0"):
    return {"id": firmware_id, "version": version, "filename": f"fw-{version}.bin", "checksum": "ab" * 32,
            "size": 4096, "uploaded_by": "admin", "created_at": "2026-10-24T12:00:00Z"}


def fw_update(update_id=1, status="REQUESTED", version="1.1.0", error=None):
    return {"id": update_id, "sensor_id": "SENSOR-001", "firmware_id": 1, "version": version, "from_version": "1.0.0",
            "status": status, "error_message": error, "requested_by": "olga", "started_at": "2026-10-24T12:00:00Z",
            "updated_at": "2026-10-24T12:00:00Z", "completed_at": None}


def json_route(page, pattern, body, status=200):
    page.route(pattern, lambda route: route.fulfill(status=status, content_type="application/json",
                                                    body=json.dumps(body)))


# ---- library ---------------------------------------------------------------------------------

def test_library_lists_images_for_everyone_but_only_admin_can_upload(open_dashboard, mock_sensors_api,
                                                                     mock_firmware_api, page):
    mock_sensors_api([sensor()])
    mock_firmware_api([image(2, "1.2.0"), image(1, "1.1.0")])
    open_dashboard("OPERATOR")
    expect(page.get_by_test_id("fw-library").locator("li")).to_have_count(2)
    expect(page.get_by_test_id("fw-image-1.2.0")).to_contain_text("4096 bytes")
    expect(page.get_by_test_id("fw-upload")).to_have_count(0)


def test_empty_library(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    expect(page.get_by_test_id("fw-library-empty")).to_be_visible()


def test_admin_uploads_raw_bytes_with_version_and_safe_filename(open_dashboard, mock_sensors_api, page, tmp_path):
    mock_sensors_api([sensor()])
    library, sent = [], []

    def handle(route):
        if route.request.method == "POST":
            sent.append((route.request.url, route.request.headers["content-type"], route.request.post_data_buffer))
            library.insert(0, image(1, "1.1.0"))
            return route.fulfill(status=201, content_type="application/json", body=json.dumps(library[0]))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(library))

    page.route("**/api/firmware*", handle)
    file = tmp_path / "my firmware.bin"
    file.write_bytes(b"\x00\x01binary")
    open_dashboard("ADMIN")
    page.get_by_test_id("fw-version").fill("1.1.0")
    page.get_by_test_id("fw-file").set_input_files(str(file))
    page.get_by_test_id("fw-upload-submit").click()

    expect(page.get_by_test_id("fw-upload-message")).to_have_text("Uploaded 1.1.0")
    expect(page.get_by_test_id("fw-image-1.1.0")).to_be_visible()
    (url, content_type, body), = sent
    assert "version=1.1.0" in url and "filename=my_firmware.bin" in url
    assert content_type == "application/octet-stream"
    assert body == b"\x00\x01binary"


def test_upload_error_shows_the_api_reason(open_dashboard, mock_sensors_api, page, tmp_path):
    mock_sensors_api([sensor()])
    page.route("**/api/firmware*", lambda route: route.fulfill(
        status=409 if route.request.method == "POST" else 200, content_type="application/json",
        body=json.dumps({"detail": "Firmware 1.1.0 already exists"} if route.request.method == "POST" else [])))
    file = tmp_path / "fw.bin"
    file.write_bytes(b"x")
    open_dashboard("ADMIN")
    page.get_by_test_id("fw-version").fill("1.1.0")
    page.get_by_test_id("fw-file").set_input_files(str(file))
    page.get_by_test_id("fw-upload-submit").click()
    expect(page.get_by_test_id("fw-upload-message")).to_have_text("Firmware 1.1.0 already exists")


def test_invalid_version_is_not_submitted(open_dashboard, mock_sensors_api, page, tmp_path):
    mock_sensors_api([sensor()])
    posts = []
    page.route("**/api/firmware*", lambda route: posts.append(1) if route.request.method == "POST"
               else route.fulfill(status=200, content_type="application/json", body="[]"))
    file = tmp_path / "fw.bin"
    file.write_bytes(b"x")
    open_dashboard("ADMIN")
    page.get_by_test_id("fw-version").fill("v1.1")
    page.get_by_test_id("fw-file").set_input_files(str(file))
    page.get_by_test_id("fw-upload-submit").click()
    page.wait_for_timeout(300)
    assert posts == []


# ---- sensor firmware panel -------------------------------------------------------------------

def open_panel(open_dashboard, mock_sensors_api, mock_firmware_api, page, role="OPERATOR", updates=()):
    s = sensor()
    s["firmware_version"] = "1.0.0"
    mock_sensors_api([s])
    mock_firmware_api([image(2, "1.1.0"), image(1, "1.0.0")])
    mock_details(page, "SENSOR-001", updates=updates)
    open_dashboard(role)
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("firmware-panel")).to_be_visible()


def test_viewer_sees_history_but_cannot_update(open_dashboard, mock_sensors_api, mock_firmware_api, page):
    open_panel(open_dashboard, mock_sensors_api, mock_firmware_api, page, role="VIEWER",
               updates=[fw_update(1, "FAILED", error="checksum mismatch; staying on 1.0.0")])
    expect(page.get_by_test_id("fw-form")).to_have_count(0)
    expect(page.get_by_test_id("fw-update-1").get_by_test_id("fw-status")).to_have_text("FAILED")
    expect(page.get_by_test_id("fw-update-1").get_by_test_id("fw-message")).to_have_text(
        "checksum mismatch; staying on 1.0.0")


def test_only_other_versions_are_offered(open_dashboard, mock_sensors_api, mock_firmware_api, page):
    open_panel(open_dashboard, mock_sensors_api, mock_firmware_api, page)
    expect(page.get_by_test_id("fw-select").locator("option")).to_have_text(["Choose a version…", "1.1.0"])
    expect(page.get_by_test_id("fw-start")).to_be_disabled()  # nothing chosen yet


def test_start_update_and_follow_its_progress(open_dashboard, mock_sensors_api, mock_firmware_api, page):
    open_panel(open_dashboard, mock_sensors_api, mock_firmware_api, page)
    updates, posted = [], []

    def handle(route):
        if route.request.method == "POST":
            posted.append(route.request.post_data_json)
            updates.insert(0, fw_update(1, "REQUESTED"))
            return route.fulfill(status=202, content_type="application/json", body=json.dumps(updates[0]))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(updates))

    page.route("**/api/sensors/SENSOR-001/firmware-updates*", handle)
    page.get_by_test_id("fw-select").select_option(label="1.1.0")
    page.get_by_test_id("fw-start").click()

    status = page.get_by_test_id("fw-update-1").get_by_test_id("fw-status")
    expect(status).to_have_text("REQUESTED")
    expect(page.get_by_test_id("fw-start")).to_have_text("Update in progress…")
    expect(page.get_by_test_id("fw-start")).to_be_disabled()
    assert posted == [{"firmware_id": 2}]

    updates[0] = fw_update(1, "VERIFYING")
    expect(status).to_have_text("VERIFYING", timeout=5000)
    updates[0] = fw_update(1, "SUCCEEDED")
    expect(status).to_have_text("SUCCEEDED", timeout=5000)
    expect(page.get_by_test_id("fw-start")).to_have_text("Update")


def test_refused_update_shows_the_reason(open_dashboard, mock_sensors_api, mock_firmware_api, page):
    open_panel(open_dashboard, mock_sensors_api, mock_firmware_api, page)
    page.route("**/api/sensors/SENSOR-001/firmware-updates*", lambda route: route.fulfill(
        status=409 if route.request.method == "POST" else 200, content_type="application/json",
        body=json.dumps({"detail": "Update 3 is still in progress"} if route.request.method == "POST" else [])))
    page.get_by_test_id("fw-select").select_option(label="1.1.0")
    page.get_by_test_id("fw-start").click()
    expect(page.get_by_test_id("fw-error")).to_have_text("Update 3 is still in progress")
