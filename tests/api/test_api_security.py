"""Security checks on the API (Phase 15g): login rate limiting, headers, hostile input."""

import pytest

from backend.app.api import auth
from backend.app.rate_limit import LoginLimiter

HOSTILE = ["' OR '1'='1", "1; DROP TABLE sensors;--", "../../etc/passwd", "%00", "<script>alert(1)</script>",
           "SENSOR-001' --", "x" * 5000, "😀", "${jndi:ldap://x}"]


def bad_login(client, username="test-viewer"):
    return client.post("/auth/login", json={"username": username, "password": "wrong-password"})


# ---- login rate limiting -----------------------------------------------------------------------

def test_sixth_failed_login_for_a_user_is_429_with_retry_after(anon_client, test_users):
    for _ in range(5):
        assert bad_login(anon_client).status_code == 401
    response = bad_login(anon_client)
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many failed attempts, try again later"}
    assert 0 < int(response.headers["retry-after"]) <= 300


def test_locked_user_cannot_log_in_even_with_the_right_password(anon_client, test_users):
    username, password = test_users["VIEWER"]
    for _ in range(5):
        bad_login(anon_client, username)
    response = anon_client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 429  # otherwise guessing could just continue


def test_lock_is_per_username_and_case_insensitive(anon_client, test_users):
    for _ in range(5):
        bad_login(anon_client, "TEST-VIEWER")
    assert bad_login(anon_client, "test-viewer").status_code == 429
    username, password = test_users["OPERATOR"]  # someone else is unaffected
    assert anon_client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_success_clears_the_count(anon_client, test_users):
    username, password = test_users["VIEWER"]
    for _ in range(4):
        bad_login(anon_client, username)
    assert anon_client.post("/auth/login", json={"username": username, "password": password}).status_code == 200
    for _ in range(4):
        assert bad_login(anon_client, username).status_code == 401  # a fresh allowance


def test_spraying_many_usernames_from_one_client_is_limited(anon_client):
    statuses = [bad_login(anon_client, f"test-spray-{i}").status_code for i in range(21)]
    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429


def test_limits_expire_after_the_window():
    now = [0.0]
    limiter = LoginLimiter(per_user=2, per_client=100, window=60, clock=lambda: now[0])
    limiter.failed("u", "c")
    limiter.failed("u", "c")
    assert limiter.retry_after("u", "c") == 60
    now[0] = 30
    assert limiter.retry_after("u", "c") == 30
    now[0] = 60
    assert limiter.retry_after("u", "c") == 0


def test_forwarded_address_is_only_trusted_behind_the_proxy(monkeypatch):
    class Req:
        headers = {"x-real-ip": "203.0.113.9"}
        client = type("C", (), {"host": "172.18.0.5"})()

    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert auth.client_address(Req()) == "172.18.0.5"  # a direct caller can't pick its own address
    monkeypatch.setenv("TRUST_PROXY", "1")
    assert auth.client_address(Req()) == "203.0.113.9"


# ---- headers -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/health", "/sensors", "/auth/me", "/nope"])
def test_security_headers_on_every_response(client, path):
    headers = client.get(path).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert headers["cache-control"] == "no-store"


def test_api_docs_still_load(anon_client):
    response = anon_client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers  # Swagger UI comes from a CDN


def test_no_cors_headers(client):
    # The dashboard is served from the same origin, so no other site may read the API from a browser.
    response = client.get("/sensors", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_server_errors_do_not_leak_internals(client, broker, headers_for):
    response = client.get("/sensors/x/telemetry?limit=abc")
    assert response.status_code == 422
    assert "Traceback" not in response.text and "sqlalchemy" not in response.text.lower()


# ---- hostile input -----------------------------------------------------------------------------

@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_path_values_are_just_unknown_sensors(client, value):
    for path in (f"/sensors/{value}", f"/sensors/{value}/telemetry", f"/sensors/{value}/alerts",
                 f"/sensors/{value}/commands", f"/sensors/{value}/firmware-updates"):
        response = client.get(path)
        assert response.status_code in (404, 422), (path, response.status_code)
        assert "Traceback" not in response.text


@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_query_values_are_rejected_or_harmless(client, value):
    assert client.get("/alerts", params={"status": value}).status_code == 422
    response = client.get("/alerts", params={"sensor_id": value})
    assert response.status_code == 200 and response.json() == []


@pytest.mark.parametrize("value", HOSTILE)
def test_hostile_login_is_an_ordinary_failure(anon_client, value):
    response = anon_client.post("/auth/login", json={"username": value[:50], "password": value[:128]})
    assert response.status_code in (401, 422)


@pytest.mark.parametrize("body, content_type", [
    (b"not json", "application/json"), (b"{\"username\": \"a\"", "application/json"),
    (b"username=a&password=b", "application/x-www-form-urlencoded"), (b"\xff\xfe", "application/json"),
])
def test_malformed_bodies_are_422(anon_client, body, content_type):
    response = anon_client.post("/auth/login", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 422


def test_sensor_table_survives_injection_attempts(client, headers_for, seeded_sensor):
    sid = seeded_sensor["sensor_id"]
    for value in HOSTILE[:3]:
        client.patch(f"/sensors/{sid}", headers=headers_for("OPERATOR"), json={"name": value[:100]})
    assert len(client.get("/sensors").json()) >= 1  # still there, still answering
    assert client.get(f"/sensors/{sid}").json()["name"] == HOSTILE[2]
