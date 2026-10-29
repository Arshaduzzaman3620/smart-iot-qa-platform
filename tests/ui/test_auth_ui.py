"""Sign-in, sign-out, session expiry, role-dependent UI and the sensor details panel (API mocked)."""

import json

from playwright.sync_api import expect

from fake_api import alert, fake_session, sensor


def telemetry_rows(sensor_id, count):
    return [{"id": 100 - i, "sensor_id": sensor_id, "timestamp": f"2026-10-24T12:00:{59 - i:02d}Z",
             "temperature": 20 + i / 10, "humidity": 40.0, "pressure": 1000.0, "light": 300.0, "battery": 80.0,
             "received_at": f"2026-10-24T12:00:{59 - i:02d}Z"} for i in range(count)]


def mock_details(page, sensor_id, readings=3, alerts=()):
    page.route(f"**/api/sensors/{sensor_id}/telemetry*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(telemetry_rows(sensor_id, readings))))
    page.route(f"**/api/sensors/{sensor_id}/alerts*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(list(alerts))))


# ---- sign in -------------------------------------------------------------------------------

def test_signed_out_user_sees_only_the_login_form(open_signed_out, mock_sensors_api, page):
    requests = []
    page.on("request", lambda r: requests.append(r.url) if "/api/" in r.url else None)
    mock_sensors_api([sensor()])
    open_signed_out()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("sensor-table")).to_have_count(0)
    page.wait_for_timeout(500)
    assert requests == []  # nothing is fetched before signing in


def test_successful_login_shows_the_dashboard_and_sends_the_token(open_signed_out, mock_sensors_api,
                                                                   mock_login_api, page):
    mock_login_api(fake_session("OPERATOR", "olga"))
    mock_sensors_api([sensor("SENSOR-001")])
    auth_headers = []
    page.on("request", lambda r: auth_headers.append(r.headers.get("authorization"))
            if r.url.endswith("/api/sensors") else None)

    open_signed_out()
    page.get_by_test_id("login-username").fill("olga")
    page.get_by_test_id("login-password").fill("secret-pass")
    page.get_by_test_id("login-submit").click()

    expect(page.get_by_test_id("sensor-row-SENSOR-001")).to_be_visible()
    expect(page.get_by_test_id("user-name")).to_have_text("olga")
    expect(page.get_by_test_id("user-role")).to_have_text("OPERATOR")
    assert auth_headers[0] == "Bearer fake-token-operator"


def test_login_sends_username_and_password_as_json(open_signed_out, page, mock_sensors_api):
    sent = []

    def handle(route):
        sent.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(fake_session()))

    page.route("**/api/auth/login", handle)
    mock_sensors_api([])
    open_signed_out()
    page.get_by_test_id("login-username").fill("vic")
    page.get_by_test_id("login-password").fill("pw-12345678")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("user-menu")).to_be_visible()
    assert sent == [{"username": "vic", "password": "pw-12345678"}]


def test_wrong_password_shows_the_api_message_and_clears_the_password(open_signed_out, mock_login_api, page):
    mock_login_api({"detail": "Invalid username or password"}, status=401)
    open_signed_out()
    page.get_by_test_id("login-username").fill("olga")
    page.get_by_test_id("login-password").fill("nope")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Invalid username or password")
    expect(page.get_by_test_id("login-password")).to_have_value("")
    expect(page.get_by_test_id("login-username")).to_have_value("olga")


def test_login_with_api_down(open_signed_out, mock_login_api, page):
    mock_login_api(abort=True)
    open_signed_out()
    page.get_by_test_id("login-username").fill("olga")
    page.get_by_test_id("login-password").fill("pw")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Cannot reach the API")


def test_empty_fields_are_not_submitted(open_signed_out, page):
    calls = []
    page.route("**/api/auth/login", lambda route: calls.append(1))
    open_signed_out()
    page.get_by_test_id("login-submit").click()
    page.wait_for_timeout(300)
    assert calls == []


# ---- session ---------------------------------------------------------------------------------

def test_session_survives_a_reload(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    expect(page.get_by_test_id("sensor-table")).to_be_visible()
    page.reload()
    expect(page.get_by_test_id("sensor-table")).to_be_visible()
    expect(page.get_by_test_id("login-form")).to_have_count(0)


def test_sign_out_returns_to_login_and_forgets_the_token(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    page.get_by_test_id("logout").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('smartiot.session')") is None


def test_expired_token_signs_out_with_a_notice(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    expect(page.get_by_test_id("sensor-table")).to_be_visible()

    mock_sensors_api({"detail": "Token expired"}, status=401)
    expect(page.get_by_test_id("login-form")).to_be_visible(timeout=8000)
    expect(page.get_by_test_id("login-notice")).to_have_text("Token expired. Please sign in again.")
    expect(page.get_by_test_id("sensor-table")).to_have_count(0)


# ---- details panel and roles ---------------------------------------------------------------

def test_clicking_a_sensor_opens_its_details_and_history(open_dashboard, mock_sensors_api, page):
    s = sensor("SENSOR-007")
    s.update(name="Freezer", location="Lab B", firmware_version="1.0.0")
    mock_sensors_api([s])
    mock_details(page, "SENSOR-007", readings=20,
                 alerts=[alert(1, "SENSOR-007", message="Battery low: 15 % (below 20 %)")])
    open_dashboard()
    page.get_by_test_id("sensor-row-SENSOR-007").get_by_test_id("sensor-id").click()

    details = page.get_by_test_id("sensor-details")
    expect(details.get_by_role("heading", level=2)).to_have_text("SENSOR-007")
    expect(page.get_by_test_id("details-name")).to_have_text("Freezer")
    expect(page.get_by_test_id("details-location")).to_have_text("Lab B")
    expect(page.get_by_test_id("details-firmware")).to_have_text("1.0.0")
    expect(page.get_by_test_id("history-table").locator("tbody tr")).to_have_count(20)
    expect(page.get_by_test_id("details-alerts")).to_contain_text("Battery low")

    page.get_by_test_id("details-close").click()
    expect(details).to_have_count(0)


def test_sensor_with_no_history(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor("NEW", latest=False)])
    mock_details(page, "NEW", readings=0)
    open_dashboard()
    page.get_by_test_id("sensor-row-NEW").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("history-empty")).to_be_visible()
    expect(page.get_by_test_id("details-alerts-empty")).to_be_visible()


def test_viewer_gets_no_edit_form(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    open_dashboard("VIEWER")
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("history-table")).to_be_visible()
    expect(page.get_by_test_id("edit-sensor")).to_have_count(0)


def test_operator_edits_name_and_location(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    sent = []

    def handle(route):
        sent.append((route.request.method, route.request.post_data_json))
        updated = sensor()
        updated.update(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(updated))

    page.route("**/api/sensors/SENSOR-001", handle)
    open_dashboard("OPERATOR")
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    page.get_by_test_id("edit-name").fill("Server room")
    page.get_by_test_id("edit-location").fill("B2")
    page.get_by_test_id("edit-save").click()
    expect(page.get_by_test_id("edit-message")).to_have_text("Saved")
    assert sent == [("PATCH", {"name": "Server room", "location": "B2"})]


def test_rejected_edit_shows_the_api_reason(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    page.route("**/api/sensors/SENSOR-001", lambda route: route.fulfill(
        status=403, content_type="application/json", body=json.dumps({"detail": "Requires role OPERATOR or higher"})))
    open_dashboard("OPERATOR")
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    page.get_by_test_id("edit-name").fill("x")
    page.get_by_test_id("edit-save").click()
    expect(page.get_by_test_id("edit-message")).to_have_text("Requires role OPERATOR or higher")


def test_markup_in_a_sensor_name_is_shown_as_text(open_dashboard, mock_sensors_api, page):
    # Stored XSS check: a name an operator typed must never become HTML.
    s = sensor()
    s["name"] = '<img src=x onerror="window.__xss=1">'
    mock_sensors_api([s])
    mock_details(page, "SENSOR-001")
    open_dashboard()
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("details-name")).to_have_text(s["name"])
    assert page.locator("img").count() == 0
    assert page.evaluate("window.__xss") is None
