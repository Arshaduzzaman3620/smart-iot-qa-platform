import json

import pytest

from browser_servers import DASHBOARD_URL


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
def mock_sensors_api(page, mock_alerts_api):
    """Replace GET /api/sensors with a canned response."""
    return _mocker(page, "**/api/sensors")


@pytest.fixture
def open_dashboard(page, dashboard_server):
    def open_():
        page.goto(DASHBOARD_URL)
        return page

    return open_

