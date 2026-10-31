"""Phase 18 dashboard features, API mocked: device search, filter, sort and rooms view, the restart
confirmation, toasts, theme, sensor addresses, reading ranges, user management and the home status."""

import json

from playwright.sync_api import expect

from browser_servers import DASHBOARD_URL
from fake_api import alert, command, fake_session, mock_details, sensor


def named(sensor_id, name, location, **kw):
    s = sensor(sensor_id, **kw)
    s["name"], s["location"] = name, location
    return s


FLEET = [
    named("SENSOR-001", "Kitchen", "Ground floor", temperature=24.0, battery=80.0),
    named("SENSOR-002", "Bedroom", "First floor", temperature=19.5, battery=15.0),
    named("SENSOR-003", "Garage", "Outside", status="OFFLINE", temperature=8.0, battery=55.0),
]


def ids(page):
    return page.get_by_test_id("sensor-table").get_by_test_id("sensor-id")


# ---- search, filter, sort --------------------------------------------------------------------------

def test_search_matches_id_name_and_room(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    search = page.get_by_test_id("device-search")
    search.fill("kitchen")
    expect(ids(page)).to_have_text(["SENSOR-001"])
    search.fill("first floor")
    expect(ids(page)).to_have_text(["SENSOR-002"])
    search.fill("sensor-003")
    expect(ids(page)).to_have_text(["SENSOR-003"])
    expect(page.get_by_test_id("devices-count")).to_have_text("Showing 1 of 3 devices")


def test_no_match_explains_and_clears(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    page.get_by_test_id("device-search").fill("attic")
    expect(page.get_by_test_id("devices-no-match")).to_contain_text("No devices match “attic”")
    page.get_by_test_id("devices-clear").click()
    expect(ids(page)).to_have_count(3)
    expect(page.get_by_test_id("device-search")).to_have_value("")


def test_status_filter_with_counts(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    expect(page.get_by_test_id("filter-offline")).to_have_text("Offline 1")
    page.get_by_test_id("filter-offline").click()
    expect(ids(page)).to_have_text(["SENSOR-003"])
    expect(page.get_by_test_id("filter-offline")).to_have_attribute("aria-checked", "true")
    page.get_by_test_id("filter-error").click()
    expect(page.get_by_test_id("devices-no-match")).to_contain_text("this filter")
    page.get_by_test_id("filter-all").click()
    expect(ids(page)).to_have_count(3)


def test_column_sort_toggles_direction(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    page.get_by_test_id("sort-temperature").click()
    expect(ids(page)).to_have_text(["SENSOR-003", "SENSOR-002", "SENSOR-001"])
    expect(page.locator("th[aria-sort=ascending]")).to_have_text("Temperature")
    page.get_by_test_id("sort-temperature").click()
    expect(ids(page)).to_have_text(["SENSOR-001", "SENSOR-002", "SENSOR-003"])
    page.get_by_test_id("sort-battery").click()
    expect(ids(page)).to_have_text(["SENSOR-002", "SENSOR-003", "SENSOR-001"])


def test_sorting_keeps_the_header_texts(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    page.get_by_test_id("sort-id").click()
    expect(page.get_by_test_id("sensor-table").locator("thead th")).to_have_text(
        ["Sensor ID", "Temperature", "Humidity", "Battery", "Status", "Last seen"])


def test_slash_key_focuses_search_but_not_while_typing(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    expect(ids(page)).to_have_count(3)
    page.locator("body").press("/")
    expect(page.get_by_test_id("device-search")).to_be_focused()
    page.get_by_test_id("device-search").press("/")  # typed into the box, not swallowed
    expect(page.get_by_test_id("device-search")).to_have_value("/")


# ---- rooms view -------------------------------------------------------------------------------------

def test_rooms_view_shows_cards_and_is_remembered(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    page.get_by_test_id("view-grid").click()
    expect(page.get_by_test_id("sensor-table")).to_have_count(0)
    card = page.get_by_test_id("device-card-SENSOR-002")
    expect(card).to_contain_text("Bedroom")
    expect(card).to_contain_text("19.5")
    expect(card).to_contain_text("Comfortable")
    expect(page.get_by_test_id("device-card-SENSOR-003")).to_contain_text("Cold")
    page.reload()
    expect(page.get_by_test_id("device-grid")).to_be_visible()  # the choice survives a reload
    page.get_by_test_id("view-list").click()
    expect(page.get_by_test_id("sensor-table")).to_be_visible()


def test_rooms_card_opens_the_details(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    mock_details(page, "SENSOR-001")
    open_dashboard()
    page.get_by_test_id("view-grid").click()
    page.get_by_test_id("device-card-SENSOR-001").click()
    expect(page.get_by_test_id("sensor-details").get_by_role("heading", level=2)).to_have_text("SENSOR-001")
    expect(page.get_by_test_id("device-card-SENSOR-001")).to_have_attribute("aria-pressed", "true")


def test_rooms_view_fits_a_phone(open_dashboard, mock_sensors_api, page):
    page.set_viewport_size({"width": 375, "height": 700})
    mock_sensors_api(FLEET)
    open_dashboard()
    page.get_by_test_id("view-grid").click()
    expect(page.get_by_test_id("device-grid")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0


# ---- restart confirmation and toasts ------------------------------------------------------------

def open_commands(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    posted = []

    def handle(route):
        if route.request.method == "POST":
            body = route.request.post_data_json
            posted.append(body)
            return route.fulfill(status=202, content_type="application/json",
                                 body=json.dumps(command(1, name=body["command"])))
        route.fulfill(status=200, content_type="application/json", body="[]")

    page.route("**/api/sensors/SENSOR-001/commands*", handle)
    open_dashboard("OPERATOR")
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    return posted


def test_restart_asks_first_and_cancel_sends_nothing(open_dashboard, mock_sensors_api, page):
    posted = open_commands(open_dashboard, mock_sensors_api, page)
    page.get_by_test_id("cmd-restart").click()
    dialog = page.get_by_test_id("confirm-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("heading")).to_have_text("Restart SENSOR-001?")
    page.get_by_test_id("confirm-cancel").click()
    expect(dialog).to_be_hidden()
    page.wait_for_timeout(300)
    assert posted == []


def test_escape_cancels_the_restart(open_dashboard, mock_sensors_api, page):
    posted = open_commands(open_dashboard, mock_sensors_api, page)
    page.get_by_test_id("cmd-restart").click()
    expect(page.get_by_test_id("confirm-dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("confirm-dialog")).to_be_hidden()
    page.wait_for_timeout(300)
    assert posted == []


def test_confirmed_restart_is_sent_and_toasted(open_dashboard, mock_sensors_api, page):
    posted = open_commands(open_dashboard, mock_sensors_api, page)
    page.get_by_test_id("cmd-restart").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("toast")).to_have_text("Restart sent to SENSOR-001")
    assert posted == [{"command": "RESTART"}]


def test_toast_disappears_by_itself(open_dashboard, mock_sensors_api, page):
    open_commands(open_dashboard, mock_sensors_api, page)
    page.get_by_test_id("cmd-request").click()
    expect(page.get_by_test_id("toast")).to_have_text("Reading request sent to SENSOR-001")
    expect(page.get_by_test_id("toast")).to_have_count(0, timeout=6000)


def test_failed_command_shows_no_success_toast(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    page.route("**/api/sensors/SENSOR-001/commands*", lambda route: route.fulfill(
        status=503 if route.request.method == "POST" else 200, content_type="application/json",
        body=json.dumps({"detail": "MQTT broker unreachable"} if route.request.method == "POST" else [])))
    open_dashboard("OPERATOR")
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    page.get_by_test_id("cmd-request").click()
    expect(page.get_by_test_id("cmd-error")).to_have_text("MQTT broker unreachable")
    expect(page.get_by_test_id("toast")).to_have_count(0)


# ---- theme ------------------------------------------------------------------------------------------

def test_theme_switch_applies_and_is_remembered(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    html = page.locator("html")
    page.get_by_test_id("theme-dark").click()
    expect(html).to_have_attribute("data-theme", "dark")
    background = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert background == "rgb(11, 16, 32)"  # --bg of the dark theme
    page.reload()
    expect(html).to_have_attribute("data-theme", "dark")
    expect(page.get_by_test_id("theme-dark")).to_have_attribute("aria-checked", "true")
    page.get_by_test_id("theme-system").click()
    expect(html).not_to_have_attribute("data-theme", "dark")


def test_light_theme_wins_over_a_dark_system_setting(open_dashboard, mock_sensors_api, page):
    page.emulate_media(color_scheme="dark")
    mock_sensors_api([sensor()])
    open_dashboard()
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(11, 16, 32)"
    page.get_by_test_id("theme-light").click()
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(243, 245, 249)"


# ---- sensor addresses -----------------------------------------------------------------------------

def test_selected_sensor_is_in_the_address_and_back_closes_it(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001")
    open_dashboard()
    page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page).to_have_url(f"{DASHBOARD_URL.rstrip('/')}/?sensor=SENSOR-001")
    page.go_back()
    expect(page.get_by_test_id("sensor-details")).to_have_count(0)
    page.go_forward()
    expect(page.get_by_test_id("sensor-details")).to_be_visible()


def test_a_bookmarked_sensor_opens_directly(page, dashboard_server, mock_sensors_api):
    mock_sensors_api([sensor("SENSOR-007")])
    mock_details(page, "SENSOR-007")
    page.add_init_script(f"sessionStorage.setItem('smartiot.session', {json.dumps(json.dumps(fake_session()))})")
    page.goto(f"{DASHBOARD_URL.rstrip('/')}/?sensor=SENSOR-007")
    expect(page.get_by_test_id("sensor-details").get_by_role("heading", level=2)).to_have_text("SENSOR-007")
    page.get_by_test_id("details-close").click()
    expect(page).to_have_url(f"{DASHBOARD_URL.rstrip('/')}/")


# ---- reading range ---------------------------------------------------------------------------------

def test_reading_range_asks_for_more_rows(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    mock_details(page, "SENSOR-001", readings=100)
    open_dashboard()
    with page.expect_request(lambda r: "/telemetry?limit=20" in r.url):
        page.get_by_test_id("sensor-row-SENSOR-001").get_by_test_id("sensor-id").click()
    expect(page.get_by_test_id("range-20")).to_have_attribute("aria-checked", "true")
    with page.expect_request(lambda r: "/telemetry?limit=50" in r.url):
        page.get_by_test_id("range-50").click()
    expect(page.get_by_test_id("range-50")).to_have_attribute("aria-checked", "true")


# ---- users (ADMIN) ---------------------------------------------------------------------------------

def fake_users_api(page, users, create_status=201, create_body=None):
    calls = []

    def handle(route):
        method, url = route.request.method, route.request.url
        calls.append((method, url.split("/api")[1]))
        if method == "POST":
            body = route.request.post_data_json
            if create_status != 201:
                return route.fulfill(status=create_status, content_type="application/json", body=json.dumps(create_body))
            user = {"username": body["username"], "role": body["role"], "created_at": "2026-10-24T12:00:00Z"}
            users.append(user)
            return route.fulfill(status=201, content_type="application/json", body=json.dumps(user))
        if method == "DELETE":
            name = url.rsplit("/", 1)[1]
            users[:] = [u for u in users if u["username"] != name]
            return route.fulfill(status=204, body="")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(users))

    page.route("**/api/users**", handle)
    return calls


def admin_users():
    return [{"username": "ui-tester", "role": "ADMIN", "created_at": "2026-10-24T11:00:00Z"},
            {"username": "olga", "role": "OPERATOR", "created_at": "2026-10-24T11:30:00Z"}]


def test_only_admins_see_users(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard("OPERATOR")
    expect(page.get_by_test_id("sensor-table")).to_be_visible()
    expect(page.get_by_test_id("users-panel")).to_have_count(0)
    expect(page.get_by_test_id("nav-users")).to_have_count(0)


def test_admin_lists_users_and_cannot_delete_self(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    fake_users_api(page, admin_users())
    open_dashboard("ADMIN")
    expect(page.get_by_test_id("users-table").locator("tbody tr")).to_have_count(2)
    expect(page.get_by_test_id("user-row-olga").get_by_test_id("user-role-cell")).to_have_value("OPERATOR")
    expect(page.get_by_test_id("user-row-ui-tester").get_by_test_id("user-delete")).to_have_count(0)
    expect(page.get_by_test_id("user-row-olga").get_by_test_id("user-delete")).to_be_visible()


def test_admin_creates_a_user(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = fake_users_api(page, admin_users())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-new-name").fill("ivan")
    page.get_by_test_id("user-new-password").fill("long-enough-1")
    page.get_by_test_id("user-new-role").select_option("OPERATOR")
    page.get_by_test_id("user-create").click()
    expect(page.get_by_test_id("user-row-ivan")).to_be_visible()
    expect(page.get_by_test_id("toast")).to_have_text("User ivan created as OPERATOR")
    expect(page.get_by_test_id("user-new-name")).to_have_value("")  # form cleared for the next one
    assert ("POST", "/users") in calls


def test_short_password_is_not_sent(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = fake_users_api(page, admin_users())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-new-name").fill("ivan")
    page.get_by_test_id("user-new-password").fill("short")
    page.get_by_test_id("user-create").click()
    page.wait_for_timeout(300)
    assert not any(method == "POST" for method, _ in calls)


def test_duplicate_user_shows_the_api_message(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    fake_users_api(page, admin_users(), create_status=409, create_body={"detail": "User olga already exists"})
    open_dashboard("ADMIN")
    page.get_by_test_id("user-new-name").fill("olga")
    page.get_by_test_id("user-new-password").fill("long-enough-1")
    page.get_by_test_id("user-create").click()
    expect(page.get_by_test_id("users-error")).to_have_text("User olga already exists")
    expect(page.get_by_test_id("toast")).to_have_count(0)


def test_delete_user_after_confirmation(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = fake_users_api(page, admin_users())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-row-olga").get_by_test_id("user-delete").click()
    expect(page.get_by_test_id("confirm-dialog").get_by_role("heading")).to_have_text("Delete olga?")
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("user-row-olga")).to_have_count(0)
    expect(page.get_by_test_id("toast")).to_have_text("User olga deleted")
    expect(page.get_by_test_id("users-error")).to_have_count(0)  # an empty 204 is not an error
    assert ("DELETE", "/users/olga") in calls


# ---- home status ----------------------------------------------------------------------------------

def test_home_status_all_clear(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET[:2])
    open_dashboard()
    expect(page.get_by_test_id("home-status-headline")).to_have_text("Everything is running smoothly")


def test_home_status_puts_critical_alerts_first(open_dashboard, mock_sensors_api, mock_alerts_api, page):
    mock_sensors_api(FLEET)
    mock_alerts_api([alert(1, severity="CRITICAL", alert_type="HIGH_TEMPERATURE", message="Hot"), alert(2)])
    open_dashboard()
    expect(page.get_by_test_id("home-status-headline")).to_have_text("1 critical alert needs attention")
    expect(page.get_by_test_id("home-status")).to_have_class("hero hero-critical")


def test_home_status_reports_offline_devices(open_dashboard, mock_sensors_api, page):
    mock_sensors_api(FLEET)
    open_dashboard()
    expect(page.get_by_test_id("home-status-headline")).to_have_text("1 of 3 devices offline")


def test_sidebar_marks_the_section_on_screen(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    open_dashboard()
    expect(page.get_by_test_id("nav-overview")).to_have_attribute("aria-current", "location")
    page.get_by_test_id("nav-firmware").click()
    expect(page.get_by_test_id("nav-firmware")).to_have_attribute("aria-current", "location")
