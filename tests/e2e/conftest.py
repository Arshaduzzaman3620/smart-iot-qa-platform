import pytest


@pytest.fixture
def stack(receiver_process, api_server, dashboard_server):
    """Broker + receiver + MySQL + API + dashboard all running. Returns the receiver log reader."""
    return receiver_process
