"""Whole stack: an MQTT message from a (fake) sensor ends up rendered on the dashboard.

Automates the manual checks in docs/testing/e2e-manual-verification.md.
"""

from datetime import datetime, timezone

import httpx
from playwright.sync_api import expect

from browser_servers import API_PORT, DASHBOARD_URL
from helpers import valid_telemetry, wait_until

API = f"http://localhost:{API_PORT}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def api_sensor(sensor_id: str):
    response = httpx.get(f"{API}/sensors")
    return next((s for s in response.json() if s["sensor_id"] == sensor_id), None)


def test_published_reading_appears_on_dashboard_with_matching_values(stack, mqtt_publisher, sensor_id, page):
    message = valid_telemetry(sensor_id, timestamp=now_iso(), temperature=23.47, humidity=51.26, battery=77.75)
    mqtt_publisher(sensor_id, message)

    # API hop: exact values.
    sensor = wait_until(lambda: api_sensor(sensor_id))
    latest = sensor["latest_telemetry"]
    for field in ("temperature", "humidity", "pressure", "light", "battery"):
        assert latest[field] == message[field], field
    assert sensor["status"] == "ONLINE"

    # Dashboard hop: the same values, rounded to 1 dp as the UI is designed to show them.
    page.goto(DASHBOARD_URL)
    row = page.get_by_test_id(f"sensor-row-{sensor_id}")
    expect(row.get_by_test_id("temperature")).to_have_text(f"{message['temperature']:.1f} °C")
    expect(row.get_by_test_id("humidity")).to_have_text(f"{message['humidity']:.1f} %")
    expect(row.get_by_test_id("battery")).to_have_text(f"{message['battery']:.1f} %")
    expect(row.get_by_test_id("status")).to_have_text("ONLINE")
    expect(row.get_by_test_id("last-seen")).to_contain_text("s ago")


def test_dashboard_updates_without_reload_when_new_reading_arrives(stack, mqtt_publisher, sensor_id, page):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp=now_iso(), temperature=10.0))
    wait_until(lambda: api_sensor(sensor_id))
    page.goto(DASHBOARD_URL)
    cell = page.get_by_test_id(f"sensor-row-{sensor_id}").get_by_test_id("temperature")
    expect(cell).to_have_text("10.0 °C")

    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp=now_iso(), temperature=11.0))
    expect(cell).to_have_text("11.0 °C", timeout=10_000)  # next 5 s poll picks it up


def test_rejected_reading_never_reaches_api_or_dashboard(stack, mqtt_publisher, sensor_id, page):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, temperature=999))
    wait_until(lambda: f"Rejected message on iot/sensors/{sensor_id}/telemetry" in stack())

    assert httpx.get(f"{API}/sensors/{sensor_id}").status_code == 404
    page.goto(DASHBOARD_URL)
    expect(page.get_by_test_id("last-updated")).to_contain_text("Updated")
    expect(page.get_by_test_id(f"sensor-row-{sensor_id}")).to_have_count(0)
