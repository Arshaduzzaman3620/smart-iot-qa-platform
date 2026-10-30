import json

import pytest

from browser_servers import DASHBOARD_URL
from fake_api import fake_session


def _mocker(page, pattern: str):
    """mock(body=[...], status=200) or mock(abort=True) replaces every request matching `pattern`."""

    def mock(body=None, status: int = 200, abort: bool = False):
        def handle(route):
            if abort:
                route.abort("connectionrefused")
            else:
                route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

        page.unroute(pattern)
        page.route(pattern, handle)

    return mock


@pytest.fixture
def mock_alerts_api(page):
    """Replace GET /api/alerts. Defaults to no active alerts, so no test reaches a real API by accident."""
    mock = _mocker(page, "**/api/alerts*")
    mock([])
    return mock


@pytest.fixture
def mock_firmware_api(page):
    """Replace GET /api/firmware (the firmware library). Defaults to none uploaded."""
    mock = _mocker(page, "**/api/firmware")
    mock([])
    return mock


@pytest.fixture
def mock_sensors_api(page, mock_alerts_api, mock_firmware_api):
    """Replace GET /api/sensors with a canned response."""
    return _mocker(page, "**/api/sensors")


@pytest.fixture
def open_dashboard(page, dashboard_server):
    """Open the dashboard already signed in (as `role`), skipping the login form."""

    def open_(role: str = "VIEWER"):
        page.add_init_script(
            f"sessionStorage.setItem('smartiot.session', {json.dumps(json.dumps(fake_session(role)))})")
        page.goto(DASHBOARD_URL)
        return page

    return open_


@pytest.fixture
def open_signed_out(page, dashboard_server):
    def open_():
        page.goto(DASHBOARD_URL)
        return page

    return open_


@pytest.fixture
def mock_login_api(page):
    return _mocker(page, "**/api/auth/login")

