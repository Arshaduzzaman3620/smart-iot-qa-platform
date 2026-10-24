import json

import pytest

from browser_servers import DASHBOARD_URL


@pytest.fixture
def mock_sensors_api(page):
    """Replace GET /api/sensors with a canned response: mock(status=200, body=[...]) or mock(abort=True)."""

    def mock(body=None, status: int = 200, abort: bool = False):
        def handle(route):
            if abort:
                route.abort("connectionrefused")
            else:
                route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

        page.unroute("**/api/sensors")
        page.route("**/api/sensors", handle)

    return mock


@pytest.fixture
def open_dashboard(page, dashboard_server):
    def open_():
        page.goto(DASHBOARD_URL)
        return page

    return open_

