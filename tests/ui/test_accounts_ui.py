"""Phase 19 in the browser, API mocked: create an account, forgot username / password, reset from the
emailed link, password field helpers, and approving sign-ups in Users."""

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


# ---- create account -------------------------------------------------------------------------------

def fill_signup(page, password="Good-Password-1!", confirm=None):
    page.get_by_test_id("auth-tab-signup").click()
    page.get_by_test_id("signup-username").fill("ann")
    page.get_by_test_id("signup-email").fill("ann@example.com")
    page.get_by_test_id("signup-password").fill(password)
    page.get_by_test_id("signup-confirm").fill(confirm if confirm is not None else password)


def test_create_account_then_back_to_sign_in(open_signed_out, page):
    sent = capture(page, "**/api/auth/register", 201,
                   {"detail": "Account created. An administrator must approve it before you can sign in."})
    open_signed_out()
    fill_signup(page)
    page.get_by_test_id("signup-submit").click()
    expect(page.get_by_test_id("signup-done")).to_contain_text("An administrator must approve it")
    assert sent == [{"username": "ann", "email": "ann@example.com", "password": "Good-Password-1!"}]
    page.get_by_test_id("back-to-signin").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    expect(page.get_by_test_id("auth-flash")).to_contain_text("once it is approved")


def test_mismatched_passwords_are_not_sent(open_signed_out, page):
    sent = capture(page, "**/api/auth/register", 201, {"detail": "ok"})
    open_signed_out()
    fill_signup(page, confirm="Something-Else-2!")
    page.get_by_test_id("signup-submit").click()
    expect(page.get_by_test_id("signup-error")).to_have_text("The passwords don't match")
    assert sent == []


def test_taken_username_shows_the_api_message(open_signed_out, page):
    capture(page, "**/api/auth/register", 409, {"detail": "Username or email already in use"})
    open_signed_out()
    fill_signup(page)
    page.get_by_test_id("signup-submit").click()
    expect(page.get_by_test_id("signup-error")).to_have_text("Username or email already in use")
    expect(page.get_by_test_id("signup-form")).to_be_visible()


def test_invalid_email_is_stopped_by_the_form(open_signed_out, page):
    sent = capture(page, "**/api/auth/register", 201, {"detail": "ok"})
    open_signed_out()
    fill_signup(page)
    page.get_by_test_id("signup-email").fill("not-an-email")
    page.get_by_test_id("signup-submit").click()
    page.wait_for_timeout(300)
    assert sent == []


def test_password_strength_and_show_toggle(open_signed_out, page):
    open_signed_out()
    page.get_by_test_id("auth-tab-signup").click()
    field = page.get_by_test_id("signup-password")
    for value, label in [("short", "Too short"), ("lowercase1", "Fair"), ("longer-password", "Good"),
                         ("Longer-Password-1!", "Strong")]:
        field.fill(value)
        expect(page.get_by_test_id("password-strength")).to_have_text(label)
    expect(field).to_have_attribute("type", "password")
    page.get_by_test_id("signup-password-toggle").click()
    expect(field).to_have_attribute("type", "text")
    expect(page.get_by_test_id("signup-password-toggle")).to_have_attribute("aria-pressed", "true")


def test_tabs_switch_between_sign_in_and_create(open_signed_out, page):
    open_signed_out()
    expect(page.get_by_test_id("auth-tab-signin")).to_have_attribute("aria-selected", "true")
    page.get_by_test_id("auth-tab-signup").click()
    expect(page.get_by_test_id("signup-form")).to_be_visible()
    expect(page.get_by_test_id("login-form")).to_have_count(0)
    page.get_by_test_id("auth-tab-signin").click()
    expect(page.get_by_test_id("login-form")).to_be_visible()


def test_pending_account_is_told_to_wait(open_signed_out, mock_login_api, page):
    mock_login_api({"detail": "Your account is waiting for an administrator's approval"}, status=403)
    open_signed_out()
    page.get_by_test_id("login-username").fill("ann")
    page.get_by_test_id("login-password").fill("Good-Password-1!")
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("login-error")).to_have_text("Your account is waiting for an administrator's approval")


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


def test_sign_in_page_fits_a_phone(open_signed_out, page):
    page.set_viewport_size({"width": 375, "height": 700})
    open_signed_out()
    expect(page.get_by_test_id("login-form")).to_be_visible()
    page.get_by_test_id("auth-tab-signup").click()
    expect(page.get_by_test_id("signup-form")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0


# ---- approving sign-ups (ADMIN) -------------------------------------------------------------------

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
            users.append({**body, "status": "ACTIVE", "created_at": "2026-10-31T09:00:00Z"})
            return route.fulfill(status=201, content_type="application/json", body=json.dumps(users[-1]))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(users))

    page.route("**/api/users**", handle)
    return calls


def people():
    return [
        {"username": "ui-tester", "role": "ADMIN", "status": "ACTIVE", "email": None, "created_at": "2026-10-24T11:00:00Z"},
        {"username": "olga", "role": "OPERATOR", "status": "ACTIVE", "email": "olga@example.com", "created_at": "2026-10-24T11:30:00Z"},
        {"username": "ann", "role": "VIEWER", "status": "PENDING", "email": "ann@example.com", "created_at": "2026-10-31T08:00:00Z"},
    ]


def test_pending_sign_ups_are_listed_apart(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    users_api(page, people())
    open_dashboard("ADMIN")
    expect(page.get_by_test_id("pending-count")).to_have_text("1 waiting")
    expect(page.get_by_test_id("pending-ann")).to_contain_text("ann@example.com")
    expect(page.get_by_test_id("user-row-ann")).to_have_count(0)  # not among the active accounts
    expect(page.get_by_test_id("user-row-olga")).to_contain_text("olga@example.com")


def test_approve_with_a_role(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = users_api(page, people())
    open_dashboard("ADMIN")
    page.get_by_test_id("pending-ann").get_by_test_id("approve-role").select_option("OPERATOR")
    page.get_by_test_id("pending-ann").get_by_test_id("approve").click()
    expect(page.get_by_test_id("toast")).to_have_text("ann approved as OPERATOR")
    expect(page.get_by_test_id("user-row-ann")).to_be_visible()
    expect(page.get_by_test_id("pending-users")).to_have_count(0)
    assert ("PATCH", "/users/ann", {"status": "ACTIVE", "role": "OPERATOR"}) in calls


def test_reject_asks_first(open_dashboard, mock_sensors_api, page):
    mock_sensors_api([sensor()])
    calls = users_api(page, people())
    open_dashboard("ADMIN")
    page.get_by_test_id("pending-ann").get_by_test_id("reject").click()
    expect(page.get_by_test_id("confirm-dialog").get_by_role("heading")).to_have_text("Reject ann?")
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("toast")).to_have_text("Sign-up from ann rejected")
    assert ("DELETE", "/users/ann", None) in calls


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
    page.get_by_test_id("user-create").click()
    expect(page.get_by_test_id("user-row-ivan")).to_contain_text("ivan@example.com")
    assert ("POST", "/users", {"username": "ivan", "password": "long-enough-1", "role": "VIEWER",
                               "email": "ivan@example.com"}) in calls
