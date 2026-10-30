"""Commands through every hop with the real simulator (Phase 15d):
API -> MQTT -> sensor -> response -> receiver -> MySQL -> API / dashboard."""

import httpx
from playwright.sync_api import expect

from browser_servers import API_URL, DASHBOARD_URL
from helpers import wait_until


def send(sensor_id, headers, **body) -> dict:
    response = httpx.post(f"{API_URL}/sensors/{sensor_id}/commands", headers=headers, json=body, timeout=10)
    assert response.status_code == 202, response.text
    return response.json()


def outcome(command_id, headers) -> dict:
    """Wait until the command is no longer SENT."""
    return wait_until(lambda: (c := httpx.get(f"{API_URL}/commands/{command_id}", headers=headers).json())
                      ["status"] != "SENT" and c, timeout=15)


def readings(sensor_id, headers) -> int:
    return len(httpx.get(f"{API_URL}/sensors/{sensor_id}/telemetry?limit=1000", headers=headers).json())


def test_sensor_metadata_arrives_from_the_device(simulated_sensor, api_headers):
    sensor_id, _ = simulated_sensor
    sensor = wait_until(lambda: (s := httpx.get(f"{API_URL}/sensors/{sensor_id}", headers=api_headers).json())
                        .get("firmware_version") and s)
    assert (sensor["name"], sensor["location"], sensor["firmware_version"]) == ("Room 1 Sensor", "Room-1", "1.0.0")


def test_request_telemetry(simulated_sensor, operator_headers):
    sensor_id, _ = simulated_sensor
    before = readings(sensor_id, operator_headers)
    result = outcome(send(sensor_id, operator_headers, command="REQUEST_TELEMETRY")["id"], operator_headers)
    assert (result["status"], result["message"]) == ("SUCCEEDED", "Reading published")
    wait_until(lambda: readings(sensor_id, operator_headers) == before + 1)


def test_set_interval_changes_the_reading_rate(simulated_sensor, operator_headers):
    sensor_id, _ = simulated_sensor
    result = outcome(send(sensor_id, operator_headers, command="SET_INTERVAL", interval=1)["id"], operator_headers)
    assert (result["status"], result["message"]) == ("SUCCEEDED", "Interval set to 1 s")
    before = readings(sensor_id, operator_headers)
    # At the start-up interval of 60 s this would take a minute; at 1 s it takes ~3 s.
    wait_until(lambda: readings(sensor_id, operator_headers) >= before + 3, timeout=10)


def test_restart_reconnects_and_reports(simulated_sensor, operator_headers):
    sensor_id, log = simulated_sensor
    result = outcome(send(sensor_id, operator_headers, command="RESTART")["id"], operator_headers)
    assert (result["status"], result["message"]) == ("SUCCEEDED", "Restarted (1 s)")
    assert "MQTT client stopped cleanly" in log()  # it really dropped off the network
    # After the reboot it reads again straight away, and keeps answering commands.
    result = outcome(send(sensor_id, operator_headers, command="REQUEST_TELEMETRY")["id"], operator_headers)
    assert result["status"] == "SUCCEEDED"


def test_operator_sends_a_command_from_the_dashboard(simulated_sensor, test_users, page):
    sensor_id, _ = simulated_sensor
    username, password = test_users["OPERATOR"]
    page.goto(DASHBOARD_URL)
    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()
    page.get_by_test_id(f"sensor-row-{sensor_id}").get_by_test_id("sensor-id").click()

    page.get_by_test_id("cmd-request").click()
    item = page.get_by_test_id("command-list").locator("li").first
    expect(item.get_by_test_id("command-status")).to_have_text("SUCCEEDED", timeout=10_000)
    expect(item.get_by_test_id("command-message")).to_have_text("Reading published")
