"""Login, tokens and role checks on every endpoint (Phase 15c)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.app import security
from backend.app.security import create_token
from helpers import TEST_PASSWORD

PROTECTED = [
    ("GET", "/sensors"), ("GET", "/sensors/X"), ("GET", "/sensors/X/telemetry"), ("GET", "/sensors/X/alerts"),
    ("GET", "/alerts"), ("GET", "/auth/me"), ("PATCH", "/sensors/X"),
    ("GET", "/users"), ("POST", "/users"), ("DELETE", "/users/someone"),
    ("POST", "/sensors/X/commands"), ("GET", "/sensors/X/commands"), ("GET", "/commands/1"),
    ("GET", "/firmware"), ("POST", "/firmware"), ("POST", "/sensors/X/firmware-updates"),
    ("GET", "/sensors/X/firmware-updates"), ("GET", "/firmware-updates/1"),
]

# 32+ bytes, so PyJWT does not warn; it is still the wrong key.
WRONG_KEY = "not-the-secret-but-long-enough-for-hs256"



# ---- POST /auth/login ---------------------------------------------------------------------

def test_login_returns_a_working_token(anon_client, test_users):
    username, password = test_users["OPERATOR"]
    response = anon_client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == security.TOKEN_MINUTES * 60
    assert body["user"]["username"] == username and body["user"]["role"] == "OPERATOR"
    assert "password_hash" not in body["user"]

    me = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == username


@pytest.mark.parametrize("username, password", [
    ("test-viewer", "wrong-password"),
    ("test-viewer", TEST_PASSWORD.upper()),
    ("test-nobody", TEST_PASSWORD),
    ("' OR '1'='1", "' OR '1'='1"),
])
def test_bad_credentials_are_401_with_one_message(anon_client, test_users, username, password):
    response = anon_client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    # Same answer for unknown user and wrong password: no username enumeration.
    assert response.json() == {"detail": "Invalid username or password"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("body", [
    {}, {"username": "a"}, {"password": "b"}, {"username": "", "password": "x"}, {"username": "x", "password": ""},
    {"username": "x" * 51, "password": "x"}, {"username": "x", "password": "x" * 129},
    {"username": 1, "password": 2}, {"username": "x", "password": "y", "role": "ADMIN"},
])
def test_malformed_login_is_422(anon_client, body):
    assert anon_client.post("/auth/login", json=body).status_code == 422


def test_rejected_password_is_never_echoed_back(anon_client):
    secret = "my-real-password-but-129-chars-" + "x" * 98
    response = anon_client.post("/auth/login", json={"username": "x", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_login_is_not_a_get(anon_client):
    assert anon_client.get("/auth/login").status_code == 405


# ---- tokens --------------------------------------------------------------------------------

@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_endpoint_needs_a_token(anon_client, method, path):
    response = anon_client.request(method, path)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize("header", [
    "Bearer not-a-jwt", "Bearer ", "Basic dXNlcjpwYXNz", "bearer", "Token abc",
])
def test_malformed_authorization_header_is_401(anon_client, header):
    assert anon_client.get("/sensors", headers={"Authorization": header}).status_code == 401


def test_expired_token_is_401_token_expired(anon_client, test_users):
    username, _ = test_users["ADMIN"]
    old = create_token(username, "ADMIN", minutes=1, now=datetime.now(timezone.utc) - timedelta(minutes=5))
    response = anon_client.get("/sensors", headers={"Authorization": f"Bearer {old}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Token expired"}


def test_token_signed_with_another_secret_is_401(anon_client, test_users):
    username, _ = test_users["ADMIN"]
    forged = jwt.encode({"sub": username, "role": "ADMIN", "exp": 9999999999}, WRONG_KEY, algorithm="HS256")
    response = anon_client.get("/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


def test_role_claim_in_token_is_not_trusted(anon_client, test_users):
    # A VIEWER's token claiming ADMIN still gets VIEWER rights: the role comes from the database.
    username, _ = test_users["VIEWER"]
    token = create_token(username, "ADMIN")
    assert anon_client.get("/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_token_for_unknown_user_is_401(anon_client):
    token = create_token("test-deleted-long-ago", "ADMIN")
    assert anon_client.get("/sensors", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---- roles ---------------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["VIEWER", "OPERATOR", "ADMIN"])
def test_every_role_can_read(client, headers_for, role):
    for path in ("/sensors", "/alerts", "/auth/me"):
        assert client.get(path, headers=headers_for(role)).status_code == 200, path


@pytest.mark.parametrize("role, status", [("VIEWER", 403), ("OPERATOR", 403), ("ADMIN", 200)])
def test_only_admin_manages_users(client, headers_for, role, status):
    assert client.get("/users", headers=headers_for(role)).status_code == status


def test_forbidden_says_which_role_is_needed(client):
    response = client.get("/users")  # default client is a VIEWER
    assert response.json() == {"detail": "Requires role ADMIN or higher"}


def test_health_stays_public(anon_client):
    assert anon_client.get("/health").status_code == 200
