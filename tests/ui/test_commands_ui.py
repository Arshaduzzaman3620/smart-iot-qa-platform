"""The commands section of the sensor details panel (Phase 15d), API mocked."""

import json

from playwright.sync_api import expect

from fake_api import command, mock_details, sensor


def open_details(open_dashboard, mock_sensors_api, page, role="OPERATOR", commands=()):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001", commands=commands)
    open_dashboard(role)
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("commands")).to_be_visible()
    return page


def fake_command_api(page, history, post_status=202, post_body=None):
    """GET returns `history` (a list the test can change); POST records the body and adds a SENT command."""
    posted = []

    def handle(route):
        if route.request.method == "POST":
            posted.append(route.request.post_data_json)
            if post_status != 202:
                return route.fulfill(status=post_status, content_type="application/json", body=json.dumps(post_body))
            body = route.request.post_data_json
            new = command(len(history) + 1, name=body["command"],
                          params={"interval": body["interval"]} if "interval" in body else {})
            history.insert(0, new)
            return route.fulfill(status=202, content_type="application/json", body=json.dumps(new))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(history))

    page.route("**/api/sensors/SENSOR-001/commands*", handle)
    return posted


def test_viewer_sees_history_but_no_buttons(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page, role="VIEWER",
                 commands=[command(1, status="SUCCEEDED", message="Reading published")])
    expect(page.get_by_test_id("cmd-request")).to_have_count(0)
    expect(page.get_by_test_id("cmd-restart")).to_have_count(0)
    expect(page.get_by_test_id("command-1").get_by_test_id("command-status")).to_have_text("SUCCEEDED")


def test_no_commands_yet(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page)
    expect(page.get_by_test_id("commands-empty")).to_have_text("No commands yet.")


def test_history_shows_status_command_message_and_requester(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page, commands=[
        command(3, name="SET_INTERVAL", params={"interval": 10}, status="SUCCEEDED", message="Interval set to 10 s"),
        command(2, name="RESTART", status="TIMED_OUT", message="No response within 30 s"),
        command(1, status="FAILED", message="MQTT broker unreachable"),
    ])
    expect(page.get_by_test_id("command-list").get_by_test_id("command-name")).to_have_text(
        ["SET_INTERVAL 10 s", "RESTART", "REQUEST_TELEMETRY"])
    expect(page.get_by_test_id("command-list").get_by_test_id("command-status")).to_have_text(
        ["SUCCEEDED", "TIMED_OUT", "FAILED"])
    expect(page.get_by_test_id("command-2").get_by_test_id("command-status")).to_have_class(
        "badge badge-cmd-timed_out")
    expect(page.get_by_test_id("command-3")).to_contain_text("by olga")


def test_each_button_sends_its_command(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page)
    posted = fake_command_api(page, [])

    page.get_by_test_id("cmd-request").click()
    expect(page.get_by_test_id("command-list").locator("li")).to_have_count(1)
    page.get_by_test_id("cmd-restart").click()
    expect(page.get_by_test_id("command-list").locator("li")).to_have_count(2)
    page.get_by_test_id("cmd-interval-value").fill("30")
    page.get_by_test_id("cmd-interval").click()
    expect(page.get_by_test_id("command-list").locator("li")).to_have_count(3)

    assert posted == [{"command": "REQUEST_TELEMETRY"}, {"command": "RESTART"},
                      {"command": "SET_INTERVAL", "interval": 30}]


def test_pending_command_updates_when_the_sensor_answers(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page)
    history = []
    fake_command_api(page, history)
    page.get_by_test_id("cmd-request").click()
    status = page.get_by_test_id("command-1").get_by_test_id("command-status")
    expect(status).to_have_text("SENT")

    history[0] = command(1, status="SUCCEEDED", message="Reading published")  # the receiver stored the answer
    expect(status).to_have_text("SUCCEEDED", timeout=5000)  # polled about every second while SENT
    expect(page.get_by_test_id("command-1").get_by_test_id("command-message")).to_have_text("Reading published")


def test_broker_down_shows_the_reason(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page)
    fake_command_api(page, [], post_status=503, post_body={"detail": "MQTT broker unreachable"})
    page.get_by_test_id("cmd-restart").click()
    expect(page.get_by_test_id("cmd-error")).to_have_text("MQTT broker unreachable")


def test_interval_out_of_range_is_not_sent(open_dashboard, mock_sensors_api, page):
    open_details(open_dashboard, mock_sensors_api, page)
    posted = fake_command_api(page, [])
    for value in ("0", "3601", "2.5"):
        page.get_by_test_id("cmd-interval-value").fill(value)
        page.get_by_test_id("cmd-interval").click()
    page.wait_for_timeout(300)
    assert posted == []  # the browser's own number validation stops it; the API would 422 it anyway
