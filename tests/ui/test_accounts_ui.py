"""Phase 19 in the browser, API mocked: no public sign-up, forgot username / password, reset from the
emailed link, password field helpers, and accounts with email in the admin's Users screen."""

import json

from playwright.sync_api import expect

from browser_servers import DASHBOARD_URL
from fake_api import sensor

ROOT = DASHBOARD_URL.rstrip("/")


def capture(page, pattern, status=200, body=None):
    """Answer POSTs to `pattern` with `status` / `body`; returns the JSON bodies that were sent."""
    sent = []

    def handle(route):
        sent.append(route.request.post_data_json)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body or {}))

    page.route(pattern, handle)
    return sent


# ---- sign-in page ----------------------------------------------------------------------------------

def test_sign_in_page_has_no_sign_up(open_signed_out, page):
    open_signed_out()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_text("Create account")).to_have_count(0)
    expect(page.get_by_test_id("no-signup-note")).to_have_text("Need an account? Ask your administrator.")


def test_show_password_toggle(open_signed_out, page):
    open_signed_out()
    field = page.get_by_test_id("login-password")
    field.fill("secret-pass")
    expect(field).to_have_attribute("type", "password")
    page.get_by_test_id("login-password-toggle").click()
    expect(field).to_have_attribute("type", "text")
    expect(page.get_by_test_id("login-password-toggle")).to_have_attribute("aria-pressed", "true")


def test_switched_off_account_is_told(open_signed_out, mock_login_api, page):
    mock_login_api({"detail": "This account is disabled. Contact your administrator."}, status=403)
    open_signed_out()
    page.get_by_test_id("login-username").fill("ann")
    page.get_by_test_id("login-password").fill("Good-Password-1!")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("This account is disabled. Contact your administrator.")


# ---- forgot and reset -------------------------------------------------------------------------------

FORGOT = "If that email belongs to an account, we have sent the username and a reset link to it."


def test_forgot_username_or_password(open_signed_out, page):
    sent = capture(page, "**/api/auth/forgot-password", 202, {"detail": FORGOT})
    open_signed_out()
    page.get_by_test_id("forgot-link").click()
    page.get_by_test_id("forgot-email").fill("ann@example.com")
    page.get_by_test_id("forgot-submit").click()
    expect(page.get_by_test_id("forgot-done")).to_contain_text(FORGOT)
    assert sent == [{"email": "ann@example.com"}]
    page.get_by_test_id("back-to-signin").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()


def test_reset_link_opens_the_new_password_form(page, dashboard_server):
    sent = capture(page, "**/api/auth/reset-password", 200, {"detail": "Password changed. You can sign in now."})
    page.goto(f"{ROOT}/?reset=tok-1234567890abcdefghijklmnop")
    expect(page.get_by_test_id("reset-form")).to_be_visible()
    page.get_by_test_id("reset-password").fill("Brand-New-Pass-2!")
    page.get_by_test_id("reset-confirm").fill("Brand-New-Pass-2!")
    page.get_by_test_id("reset-submit").click()
    expect(page.get_by_test_id("auth-flash")).to_have_text("Password changed. You can sign in now.")
    expect(page).to_have_url(f"{ROOT}/")  # the used link is taken out of the address
    assert sent == [{"token": "tok-1234567890abcdefghijklmnop", "password": "Brand-New-Pass-2!"}]


def test_expired_reset_link_offers_a_new_one(page, dashboard_server):
    capture(page, "**/api/auth/reset-password", 400, {"detail": "This reset link is invalid or has expired. Ask for a new one."})
    page.goto(f"{ROOT}/?reset=tok-1234567890abcdefghijklmnop")
    page.get_by_test_id("reset-password").fill("Brand-New-Pass-2!")
    page.get_by_test_id("reset-confirm").fill("Brand-New-Pass-2!")
    page.get_by_test_id("reset-submit").click()
    expect(page.get_by_test_id("reset-error")).to_contain_text("expired")
    page.get_by_test_id("reset-new-link").click()
    expect(page.get_by_test_id("forgot-form")).to_be_visible()


def test_reset_mismatch_is_not_sent(page, dashboard_server):
    sent = capture(page, "**/api/auth/reset-password", 200, {"detail": "ok"})
    page.goto(f"{ROOT}/?reset=tok-1234567890abcdefghijklmnop")
    page.get_by_test_id("reset-password").fill("Brand-New-Pass-2!")
    page.get_by_test_id("reset-confirm").fill("Brand-New-Pass-3!")
    page.get_by_test_id("reset-submit").click()
    expect(page.get_by_test_id("reset-error")).to_have_text("The passwords don't match")
    assert sent == []


def test_new_password_strength(page, dashboard_server):
    page.goto(f"{ROOT}/?reset=tok-1234567890abcdefghijklmnop")
    field = page.get_by_test_id("reset-password")
    for value, label in [("short", "Too short"), ("lowercase1", "Fair"), ("longer-password", "Good"),
                         ("Longer-Password-1!", "Strong")]:
        field.fill(value)
        expect(page.get_by_test_id("password-strength")).to_have_text(label)


def test_sign_in_page_fits_a_phone(open_signed_out, page):
    page.set_viewport_size({"width": 375, "height": 700})
    open_signed_out()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    page.get_by_test_id("forgot-link").click()
    expect(page.get_by_test_id("forgot-form")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0


# ---- accounts in Users (ADMIN) --------------------------------------------------------------------

def users_api(page, users):
    calls = []

    def handle(route):
        method, url = route.request.method, route.request.url
        calls.append((method, url.split("/api")[1], route.request.post_data_json if method in ("POST", "PATCH") else None))
        if method == "PATCH":
            name, body = url.rsplit("/", 1)[1], route.request.post_data_json
            for u in users:
                if u["username"] == name:
                    u.update(body)
                    return route.fulfill(status=200, content_type="application/json", body=json.dumps(u))
        if method == "DELETE":
            users[:] = [u for u in users if u["username"] != url.rsplit("/", 1)[1]]
            return route.fulfill(status=204, body="")
        if method == "POST":
            body = route.request.post_data_json
            users.append({**body, "created_at": "2026-10-31T09:00:00Z"})
            return route.fulfill(status=201, content_type="application/json", body=json.dumps(users[-1]))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(users))

    page.route("**/api/users**", handle)
    return calls


def people():
    return [
        {"username": "ui-tester", "role": "ADMIN", "email": None, "created_at": "2026-10-24T11:00:00Z"},
        {"username": "olga", "role": "OPERATOR", "email": "olga@example.com", "created_at": "2026-10-24T11:30:00Z"},
    ]


def test_users_show_emails_and_the_add_form(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    users_api(page, people())
    open_dashboard("ADMIN")
    expect(page.get_by_test_id("users-panel").get_by_role("heading", name="Add a user")).to_be_visible()
    expect(page.get_by_test_id("user-row-olga")).to_contain_text("olga@example.com")


def test_change_a_role(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = users_api(page, people())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-row-olga").get_by_test_id("user-role-cell").select_option("ADMIN")
    expect(page.get_by_test_id("toast")).to_have_text("olga is now ADMIN")
    assert ("PATCH", "/users/olga", {"role": "ADMIN"}) in calls
    # Your own role is shown, not editable.
    expect(page.get_by_test_id("user-row-ui-tester").locator("select")).to_have_count(0)


def test_admin_adds_a_user_with_email(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = users_api(page, people())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-new-name").fill("ivan")
    page.get_by_test_id("user-new-email").fill("ivan@example.com")
    page.get_by_test_id("user-new-password").fill("long-enough-1")
    page.get_by_test_id("user-new-role").select_option("OPERATOR")
    page.get_by_test_id("user-create").click()
    expect(page.get_by_test_id("user-row-ivan")).to_contain_text("ivan@example.com")
    expect(page.get_by_test_id("toast")).to_have_text("User ivan created as OPERATOR")
    assert ("POST", "/users", {"username": "ivan", "password": "long-enough-1", "role": "OPERATOR",
                               "email": "ivan@example.com"}) in calls


def test_admin_deletes_a_user_after_confirming(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = users_api(page, people())
    open_dashboard("ADMIN")
    page.get_by_test_id("user-row-olga").get_by_test_id("user-delete").click()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("user-row-olga")).to_have_count(0)
    assert ("DELETE", "/users/olga", None) in calls
