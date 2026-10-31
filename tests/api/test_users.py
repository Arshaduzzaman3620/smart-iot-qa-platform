"""User management (ADMIN only) and sensor metadata edits (OPERATOR+)."""

import pytest

from database.models import Sensor, User
from database.session import SessionLocal
from helpers import TEST_USER_PREFIX


@pytest.fixture
def admin(headers_for):
    return headers_for("ADMIN")


@pytest.fixture
def new_username(sensor_id):
    # Unique per test, cleaned up with the other test-* users.
    return f"{TEST_USER_PREFIX}{sensor_id[5:].lower()}"


# ---- /users --------------------------------------------------------------------------------

def test_admin_creates_user_who_can_then_log_in(client, anon_client, admin, new_username):
    response = client.post("/users", headers=admin,
                           json={"username": new_username, "password": "long-enough-1", "role": "OPERATOR"})
    assert response.status_code == 201
    assert response.json()["username"] == new_username and response.json()["role"] == "OPERATOR"
    assert "password" not in response.text

    login = anon_client.post("/auth/login", json={"username": new_username, "password": "long-enough-1"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "OPERATOR"


def test_password_is_stored_hashed(client, admin, new_username):
    client.post("/users", headers=admin, json={"username": new_username, "password": "plain-text-pw"})
    with SessionLocal() as session:
        stored = session.query(User).filter_by(username=new_username).one().password_hash
    assert stored.startswith("scrypt$")
    assert "plain-text-pw" not in stored


def test_role_defaults_to_viewer(client, admin, new_username):
    response = client.post("/users", headers=admin, json={"username": new_username, "password": "long-enough-1"})
    assert response.json()["role"] == "VIEWER"


def test_duplicate_username_is_409(client, admin, test_users):
    username, _ = test_users["VIEWER"]
    response = client.post("/users", headers=admin, json={"username": username, "password": "long-enough-1"})
    assert response.status_code == 409


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": "long-enough-1"},                     # 3 chars minimum
    {"username": "x" * 51, "password": "long-enough-1"},                 # column is 50
    {"username": "has space", "password": "long-enough-1"},
    {"username": "<script>", "password": "long-enough-1"},
    {"username": "ok-name", "password": "1234567"},                       # 8 chars minimum
    {"username": "ok-name", "password": "x" * 129},
    {"username": "ok-name", "password": "long-enough-1", "role": "SUPERUSER"},
    {"username": "ok-name", "password": "long-enough-1", "role": "admin"},
    {"username": "ok-name", "password": "long-enough-1", "is_admin": True},
    {"username": "ok-name"},
])
def test_invalid_new_user_is_422(client, admin, body):
    assert client.post("/users", headers=admin, json=body).status_code == 422


def test_boundary_lengths_are_accepted(client, admin, sensor_id):
    username = (TEST_USER_PREFIX + sensor_id.lower()).ljust(50, "x")
    response = client.post("/users", headers=admin, json={"username": username, "password": "x" * 8})
    assert response.status_code == 201


def test_list_users_never_exposes_hashes(client, admin, test_users):
    response = client.get("/users", headers=admin)
    assert response.status_code == 200
    names = [u["username"] for u in response.json()]
    assert set(name for name, _ in test_users.values()) <= set(names)
    assert names == sorted(names)
    assert "scrypt$" not in response.text and "password" not in response.text


def test_delete_user_revokes_their_token_at_once(client, admin, new_username, anon_client):
    client.post("/users", headers=admin, json={"username": new_username, "password": "long-enough-1"})
    token = anon_client.post("/auth/login", json={"username": new_username, "password": "long-enough-1"}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    assert anon_client.get("/sensors", headers=headers).status_code == 200

    assert client.delete(f"/users/{new_username}", headers=admin).status_code == 204
    assert anon_client.get("/sensors", headers=headers).status_code == 401


def test_admin_cannot_delete_themselves(client, admin, test_users):
    username, _ = test_users["ADMIN"]
    response = client.delete(f"/users/{username}", headers=admin)
    assert response.status_code == 400
    assert client.get("/users", headers=admin).status_code == 200  # still there


def test_delete_unknown_user_is_404(client, admin):
    assert client.delete("/users/test-never-existed", headers=admin).status_code == 404


@pytest.mark.parametrize("role", ["VIEWER", "OPERATOR"])
def test_non_admin_cannot_create_or_delete(client, headers_for, test_users, role, new_username):
    headers = headers_for(role)
    assert client.post("/users", headers=headers,
                       json={"username": new_username, "password": "long-enough-1", "role": "ADMIN"}).status_code == 403
    victim, _ = test_users["VIEWER"]
    assert client.delete(f"/users/{victim}", headers=headers).status_code == 403


# ---- PATCH /sensors/{id} -------------------------------------------------------------------

@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN"])
def test_operator_and_admin_can_rename_a_sensor(client, headers_for, seeded_sensor, role):
    sid = seeded_sensor["sensor_id"]
    response = client.patch(f"/sensors/{sid}", headers=headers_for(role),
                            json={"name": "  Freezer 2  ", "location": "Lab B"})
    assert response.status_code == 200
    assert response.json()["name"] == "Freezer 2"  # trimmed
    assert response.json()["location"] == "Lab B"
    assert client.get(f"/sensors/{sid}").json()["name"] == "Freezer 2"


def test_viewer_cannot_change_a_sensor(client, seeded_sensor):
    response = client.patch(f"/sensors/{seeded_sensor['sensor_id']}", json={"name": "hacked"})
    assert response.status_code == 403
    with SessionLocal() as session:
        assert session.query(Sensor).filter_by(sensor_id=seeded_sensor["sensor_id"]).one().name is None


def test_only_sent_fields_change(client, headers_for, seeded_sensor):
    sid, headers = seeded_sensor["sensor_id"], headers_for("OPERATOR")
    client.patch(f"/sensors/{sid}", headers=headers, json={"name": "A", "location": "L"})
    response = client.patch(f"/sensors/{sid}", headers=headers, json={"location": "M"})
    assert response.json()["name"] == "A" and response.json()["location"] == "M"


def test_empty_string_clears_a_field(client, headers_for, seeded_sensor):
    sid, headers = seeded_sensor["sensor_id"], headers_for("OPERATOR")
    client.patch(f"/sensors/{sid}", headers=headers, json={"name": "A"})
    assert client.patch(f"/sensors/{sid}", headers=headers, json={"name": "   "}).json()["name"] is None


def test_markup_is_stored_as_plain_text(client, headers_for, seeded_sensor):
    # The API stores it verbatim; the dashboard renders it as text (see the UI test).
    name = '<img src=x onerror="alert(1)">'
    response = client.patch(f"/sensors/{seeded_sensor['sensor_id']}", headers=headers_for("OPERATOR"),
                            json={"name": name})
    assert response.json()["name"] == name


@pytest.mark.parametrize("body", [
    {}, {"name": "x" * 101}, {"location": "x" * 101}, {"name": "tab\there"}, {"name": "nul\u0000"},
    {"status": "ONLINE"}, {"battery": 100}, {"sensor_id": "OTHER"}, {"name": 5},
])
def test_invalid_sensor_update_is_422(client, headers_for, seeded_sensor, body):
    response = client.patch(f"/sensors/{seeded_sensor['sensor_id']}", headers=headers_for("OPERATOR"), json=body)
    assert response.status_code == 422


def test_name_of_exactly_100_chars_is_accepted(client, headers_for, seeded_sensor):
    response = client.patch(f"/sensors/{seeded_sensor['sensor_id']}", headers=headers_for("OPERATOR"),
                            json={"name": "x" * 100})
    assert response.status_code == 200


def test_update_unknown_sensor_is_404(client, headers_for):
    assert client.patch("/sensors/TEST-NOPE", headers=headers_for("OPERATOR"), json={"name": "x"}).status_code == 404
