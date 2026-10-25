from sqlalchemy.exc import OperationalError

from backend.app.deps import get_db
from backend.app.main import app


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


class _BrokenSession:
    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("Can't connect to MySQL server"))

    scalars = scalar = execute


def _broken_db():
    yield _BrokenSession()


def test_health_reports_degraded_when_database_down(client):
    app.dependency_overrides[get_db] = _broken_db
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_endpoints_return_clean_503_when_database_down(client):
    app.dependency_overrides[get_db] = _broken_db
    try:
        responses = [client.get(path) for path in ("/sensors", "/sensors/X", "/sensors/X/telemetry")]
    finally:
        app.dependency_overrides.clear()
    for response in responses:
        assert response.status_code == 503
        # No stack trace or connection details leak to the client.
        assert response.json() == {"detail": "Database unavailable"}
