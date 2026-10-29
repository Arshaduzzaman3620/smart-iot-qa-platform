import pytest
from playwright.sync_api import expect

from browser_servers import API_URL, DASHBOARD_URL
from helpers import login_headers


@pytest.fixture
def stack(receiver_process, api_server, dashboard_server, test_users):
    """Broker + receiver + MySQL + API + dashboard all running. Returns the receiver log reader."""
    return receiver_process


@pytest.fixture
def api_headers(stack, test_users):
    """Authorization header for the running API, obtained through the real login endpoint."""
    return login_headers(API_URL, *test_users["VIEWER"])


@pytest.fixture
def open_signed_in(stack, test_users, page):
    """Open the dashboard and sign in through the login form, as a VIEWER."""

    def open_():
        username, password = test_users["VIEWER"]
        page.goto(DASHBOARD_URL)
        page.get_by_test_id("login-username").fill(username)
        page.get_by_test_id("login-password").fill(password)
        page.get_by_test_id("login-submit").click()
        expect(page.get_by_test_id("user-name")).to_have_text(username)
        return page

    return open_
