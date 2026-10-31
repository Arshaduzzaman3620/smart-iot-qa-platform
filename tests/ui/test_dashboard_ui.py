"""Dashboard behaviour with the API mocked, so every state is deterministic."""

import json
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from fake_api import alert, sensor


NOW = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def iso(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(page, sensor_id):
    return page.get_by_test_id(f"sensor-row-{sensor_id}")


def test_renders_one_row_per_sensor_with_formatted_values(open_dashboard, mock_sensors_api, page):
    # Freeze the browser's clock (timers keep running) so relative times are exact.
    page.clock.set_fixed_time(NOW)
    mock_sensors_api([sensor("SENSOR-001", temperature=22.46, humidity=48.04, battery=91.87, last_seen=iso(5)),
                      sensor("SENSOR-002", temperature=-3.05, humidity=100, battery=50, last_seen=iso(120))])
    page = open_dashboard()

    expect(page.get_by_test_id("sensor-table").locator("tbody tr")).to_have_count(2)
    first = row(page, "SENSOR-001")
    expect(first.get_by_test_id("sensor-id")).to_have_text("SENSOR-001")
    expect(first.get_by_test_id("temperature")).to_have_text("22.5 °C")
    expect(first.get_by_test_id("humidity")).to_have_text("48.0 %")
    expect(first.get_by_test_id("battery")).to_have_text("91.9 %")
    expect(first.get_by_test_id("status")).to_have_text("ONLINE")
    expect(first.get_by_test_id("last-seen")).to_have_text("5s ago")

    second = row(page, "SENSOR-002")
    expect(second.get_by_test_id("temperature")).to_have_text("-3.0 °C")  # toFixed rounds -3.05 to -3.0
    expect(second.get_by_test_id("last-seen")).to_have_text("2m ago")


def test_table_headers(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor()])
    page = open_dashboard()
    headers = page.get_by_test_id("sensor-table").locator("thead th")
    expect(headers).to_have_text(["Sensor ID", "Temperature", "Humidity", "Battery", "Status", "Last seen"])


def test_low_battery_is_highlighted_below_20_percent(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor("LOW", battery=19.99), sensor("EDGE", battery=20.0)])
    page = open_dashboard()
    expect(row(page, "LOW").get_by_test_id("battery")).to_have_class("num low")
    expect(row(page, "EDGE").get_by_test_id("battery")).to_have_class("num")


def test_status_badges(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor("A", status="ONLINE"), sensor("B", status="OFFLINE"), sensor("C", status="ERROR")])
    page = open_dashboard()
    for sensor_id, status in (("A", "online"), ("B", "offline"), ("C", "error")):
        badge = row(page, sensor_id).get_by_test_id("status")
        expect(badge).to_have_class(f"badge badge-{status}")


def test_sensor_without_readings_shows_placeholders(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor("NEW", latest=False, battery=None, last_seen=None)])
    page = open_dashboard()
    new = row(page, "NEW")
    expect(new.get_by_test_id("temperature")).to_have_text("—")
    expect(new.get_by_test_id("battery")).to_have_text("—")
    expect(new.get_by_test_id("last-seen")).to_have_text("never")


def test_empty_state(open_dashboard, mock_sensors_api):
    mock_sensors_api([])
    page = open_dashboard()
    expect(page.get_by_test_id("sensors-empty")).to_be_visible()
    expect(page.get_by_test_id("sensor-table")).to_have_count(0)


def test_database_unavailable_banner(open_dashboard, mock_sensors_api):
    mock_sensors_api({"detail": "Database unavailable"}, status=503)
    page = open_dashboard()
    expect(page.get_by_test_id("error-banner")).to_have_text("Database unavailable. Retrying…")
    expect(page.get_by_test_id("last-updated")).to_have_text("Not connected")


def test_api_unreachable_banner(open_dashboard, mock_sensors_api):
    mock_sensors_api(abort=True)
    page = open_dashboard()
    expect(page.get_by_test_id("error-banner")).to_have_text("Cannot reach the API. Retrying…")


def test_keeps_last_data_on_failure_and_recovers(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor("SENSOR-001")])
    page = open_dashboard()
    expect(row(page, "SENSOR-001")).to_be_visible()

    mock_sensors_api({"detail": "Database unavailable"}, status=503)
    banner = page.get_by_test_id("error-banner")
    expect(banner).to_have_text("Database unavailable. Showing last known data.", timeout=8000)
    expect(row(page, "SENSOR-001")).to_be_visible()

    mock_sensors_api([sensor("SENSOR-001"), sensor("SENSOR-002")])
    expect(banner).to_have_count(0, timeout=8000)
    expect(row(page, "SENSOR-002")).to_be_visible()


def test_renders_100_sensors(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor(f"SENSOR-{i:03d}", temperature=20 + i / 10) for i in range(1, 101)])
    page = open_dashboard()
    expect(page.get_by_test_id("sensor-table").locator("tbody tr")).to_have_count(100)
    expect(row(page, "SENSOR-100").get_by_test_id("temperature")).to_have_text("30.0 °C")


def test_no_horizontal_page_scroll_on_phone_width(open_dashboard, mock_sensors_api, page):
    page.set_viewport_size({"width": 375, "height": 700})
    mock_sensors_api([sensor()])
    open_dashboard()
    expect(page.get_by_test_id("sensor-table")).to_be_visible()
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0


def test_no_active_alerts_message(open_dashboard, mock_sensors_api):
    mock_sensors_api([sensor()])
    page = open_dashboard()
    expect(page.get_by_test_id("alerts-none")).to_have_text("No active alerts.")
    expect(page.get_by_test_id("alerts-panel")).to_have_count(0)


def test_active_alerts_panel(open_dashboard, mock_sensors_api, mock_alerts_api, page):
    page.clock.set_fixed_time(NOW)
    mock_sensors_api([sensor("SENSOR-001"), sensor("SENSOR-002", status="OFFLINE")])
    mock_alerts_api([
        alert(2, "SENSOR-002", "OFFLINE", "WARNING", 45, "No telemetry for 45 s (timeout 30 s)", created_at=iso(90)),
        alert(1, "SENSOR-001", "HIGH_TEMPERATURE", "CRITICAL", 72.5, "Temperature high: 72.5 °C (above 70 °C)",
              created_at=iso(30)),
    ])
    page = open_dashboard()

    panel = page.get_by_test_id("alerts-panel")
    expect(panel.get_by_role("heading")).to_have_text("Active alerts (2)")
    expect(panel.locator("li")).to_have_count(2)
    critical = page.get_by_test_id("alert-1")
    expect(critical.get_by_test_id("alert-severity")).to_have_text("CRITICAL")
    expect(critical.get_by_test_id("alert-severity")).to_have_class("badge badge-critical")
    expect(critical.get_by_test_id("alert-sensor")).to_have_text("SENSOR-001")
    expect(critical.get_by_test_id("alert-message")).to_have_text("Temperature high: 72.5 °C (above 70 °C)")
    expect(critical.get_by_test_id("alert-since")).to_have_text("30s ago")
    expect(page.get_by_test_id("alert-2").get_by_test_id("alert-severity")).to_have_class("badge badge-warning")


def test_alert_appears_and_clears_on_refresh(open_dashboard, mock_sensors_api, mock_alerts_api):
    mock_sensors_api([sensor()])
    page = open_dashboard()
    expect(page.get_by_test_id("alerts-none")).to_be_visible()

    mock_alerts_api([alert()])
    expect(page.get_by_test_id("alert-1")).to_be_visible(timeout=8000)

    mock_alerts_api([])
    expect(page.get_by_test_id("alerts-none")).to_be_visible(timeout=8000)


def test_alerts_api_failure_shows_error_banner(open_dashboard, mock_sensors_api, mock_alerts_api):
    mock_sensors_api([sensor()])
    mock_alerts_api({"detail": "Database unavailable"}, status=503)
    page = open_dashboard()
    expect(page.get_by_test_id("error-banner")).to_have_text("Database unavailable. Retrying…")


def test_critical_alerts_are_listed_first(open_dashboard, mock_sensors_api, mock_alerts_api):
    mock_sensors_api([sensor()])
    # API order is newest first: two warnings, then an older critical alert.
    mock_alerts_api([alert(3, severity="WARNING"), alert(2, severity="WARNING"), alert(1, severity="CRITICAL")])
    page = open_dashboard()
    expect(page.get_by_test_id("alerts-panel").get_by_test_id("alert-severity")).to_have_text(
        ["CRITICAL", "WARNING", "WARNING"])
    expect(page.get_by_test_id("alerts-panel").locator("li").first).to_have_attribute("data-testid", "alert-1")


def test_slow_response_is_not_cancelled_by_the_next_poll(open_dashboard, mock_alerts_api, mock_firmware_api, page):
    # An API slower than the 5 s refresh must still get its data on screen.
    page.clock.install()
    held = []
    page.route("**/api/sensors", lambda route: held.append(route))  # hold requests open, unanswered
    open_dashboard()
    # Dev StrictMode mounts twice: the first request is aborted on cleanup, the second is the live one.
    # Wait for it rather than a fixed delay -- with more requests at startup, 300 ms wasn't always enough.
    for _ in range(100):
        if len(held) >= 2:
            break
        page.wait_for_timeout(50)
    pending = held[-1]

    page.clock.run_for(6000)  # the next poll comes due while that request is still pending
    pending.fulfill(status=200, content_type="application/json", body=json.dumps([sensor("SLOW-1")]))

    expect(row(page, "SLOW-1")).to_be_visible()
