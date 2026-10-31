"""Accounts (Phase 19): accounts with email created by an admin (no public sign-up), forgot username /
password, reset links, and the schema upgrade. Emails are captured instead of sent."""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, text, update

from backend.app import mailer
from backend.app.api.auth import BAD_RESET_DETAIL, DISABLED_DETAIL, FORGOT_DETAIL
from backend.app.security import create_token, hash_password
from database.migrations import upgrade
from database.models import PasswordReset, User
from database.session import SessionLocal, engine
from helpers import TEST_USER_PREFIX

PASSWORD = "first-password-1"


@pytest.fixture
def outbox(monkeypatch):
    """Every email the API would send: [(to, subject, body)]."""
    sent = []
    monkeypatch.setattr(mailer, "send_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


def new_name() -> str:
    return f"{TEST_USER_PREFIX}acct-{uuid.uuid4().hex[:8]}"


def db_user(username) -> User | None:
    with SessionLocal() as session:
        return session.scalar(select(User).where(User.username == username))


def active_user(email=None, password=PASSWORD, role="VIEWER") -> tuple[str, str]:
    username = new_name()
    email = email or f"{username}@example.test"
    with SessionLocal() as session, session.begin():
        session.add(User(username=username, email=email, password_hash=hash_password(password), role=role))
    return username, email


def login(anon_client, username, password=PASSWORD):
    return anon_client.post("/auth/login", json={"username": username, "password": password})


def reset_token(body: str) -> str:
    return re.search(r"\?reset=([A-Za-z0-9_-]+)", body).group(1)


# ---- accounts are created by an admin -------------------------------------------------------------

def test_there_is_no_public_sign_up(anon_client):
    username = new_name()
    response = anon_client.post("/auth/register", json={"username": username, "email": f"{username}@example.test",
                                                         "password": PASSWORD})
    assert response.status_code in (404, 405)
    assert db_user(username) is None


def test_admin_creates_a_user_with_an_email_and_they_are_welcomed(client, headers_for, outbox):
    username = new_name()
    response = client.post("/users", json={"username": username, "password": PASSWORD, "role": "OPERATOR",
                                           "email": f"{username}@Example.test"}, headers=headers_for("ADMIN"))
    assert response.status_code == 201
    assert response.json()["email"] == f"{username}@example.test"  # stored trimmed and lower-case
    (to, subject, body), = outbox
    assert to == f"{username}@example.test" and subject == "Your SmartIoT account"
    assert f"Username: {username}" in body and "https://localhost:8443/" in body
    assert PASSWORD not in body  # the password is never emailed


def test_a_user_without_an_email_gets_no_email(client, headers_for, outbox):
    response = client.post("/users", json={"username": new_name(), "password": PASSWORD}, headers=headers_for("ADMIN"))
    assert response.status_code == 201 and response.json()["email"] is None
    assert outbox == []


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "two@@example.test"])
def test_invalid_email_is_422(client, headers_for, email):
    body = {"username": new_name(), "password": PASSWORD, "email": email}
    assert client.post("/users", json=body, headers=headers_for("ADMIN")).status_code == 422


def test_email_is_unique_regardless_of_case(client, headers_for, outbox):
    _, email = active_user()
    body = {"username": new_name(), "password": PASSWORD, "email": email.upper()}
    assert client.post("/users", json=body, headers=headers_for("ADMIN")).status_code == 409


@pytest.mark.parametrize("role", ["VIEWER", "OPERATOR"])
def test_only_admins_create_accounts(client, headers_for, role):
    body = {"username": new_name(), "password": PASSWORD, "email": f"{uuid.uuid4().hex[:6]}@example.test"}
    assert client.post("/users", json=body, headers=headers_for(role)).status_code == 403


def test_users_list_shows_emails(client, headers_for):
    username, email = active_user()
    users = {u["username"]: u for u in client.get("/users", headers=headers_for("ADMIN")).json()}
    assert users[username]["email"] == email


def test_admin_changes_a_role_and_it_takes_effect_at_once(anon_client, client, headers_for):
    username, _ = active_user()
    token = login(anon_client, username).json()["access_token"]
    assert anon_client.get("/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    response = client.patch(f"/users/{username}", json={"role": "ADMIN"}, headers=headers_for("ADMIN"))
    assert response.status_code == 200 and response.json()["role"] == "ADMIN"
    assert anon_client.get("/users", headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.parametrize("role", ["VIEWER", "OPERATOR"])
def test_only_admins_change_roles(client, headers_for, role):
    username, _ = active_user()
    assert client.patch(f"/users/{username}", json={"role": "ADMIN"}, headers=headers_for(role)).status_code == 403
    assert db_user(username).role == "VIEWER"


def test_admin_cannot_change_their_own_account(client, headers_for, test_users):
    admin, _ = test_users["ADMIN"]
    assert client.patch(f"/users/{admin}", json={"role": "VIEWER"}, headers=headers_for("ADMIN")).status_code == 400


@pytest.mark.parametrize("body", [{}, {"role": "ROOT"}, {"status": "ACTIVE"}, {"role": "ADMIN", "email": "x@y.z"}])
def test_update_validation(client, headers_for, body):
    username, _ = active_user()
    assert client.patch(f"/users/{username}", json=body, headers=headers_for("ADMIN")).status_code == 422


def test_update_unknown_user_is_404(client, headers_for):
    assert client.patch(f"/users/{new_name()}", json={"role": "VIEWER"}, headers=headers_for("ADMIN")).status_code == 404


def test_a_switched_off_account_cannot_sign_in_or_use_its_token(anon_client):
    username, _ = active_user()
    token = login(anon_client, username).json()["access_token"]
    with SessionLocal() as session, session.begin():
        session.execute(update(User).where(User.username == username).values(status="DISABLED"))
    right = login(anon_client, username)
    assert right.status_code == 403 and right.json()["detail"] == DISABLED_DETAIL
    wrong = login(anon_client, username, "not-the-password")
    assert wrong.status_code == 401  # a wrong password says nothing about the account
    assert anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---- forgot username / password ---------------------------------------------------------------

def test_forgot_sends_the_username_and_a_link(anon_client, outbox):
    username, email = active_user()
    response = anon_client.post("/auth/forgot-password", json={"email": email.upper()})
    assert response.status_code == 202 and response.json()["detail"] == FORGOT_DETAIL
    (to, subject, body), = outbox
    assert to == email and f"Your username is: {username}" in body
    assert "https://localhost:8443/?reset=" in body
    # Only a hash is stored: the token from the email is not in the database.
    with SessionLocal() as session:
        stored = session.scalars(select(PasswordReset.token_hash)).all()
    assert reset_token(body) not in stored


@pytest.mark.parametrize("email", ["nobody-here@example.test", "UNKNOWN@example.test"])
def test_forgot_for_an_unknown_address_looks_the_same_and_sends_nothing(anon_client, outbox, email):
    response = anon_client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 202 and response.json()["detail"] == FORGOT_DETAIL
    assert outbox == []


def test_forgot_for_a_switched_off_account_sends_nothing(anon_client, outbox):
    username, email = active_user()
    with SessionLocal() as session, session.begin():
        session.execute(update(User).where(User.username == username).values(status="DISABLED"))
    anon_client.post("/auth/forgot-password", json={"email": email})
    assert outbox == []


def test_forgot_is_rate_limited_per_address(anon_client, outbox):
    _, email = active_user()
    codes = [anon_client.post("/auth/forgot-password", json={"email": email}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]
    assert len(outbox) == 3


# ---- reset ------------------------------------------------------------------------------------------

def ask_reset(anon_client, outbox, email) -> str:
    outbox.clear()
    anon_client.post("/auth/forgot-password", json={"email": email})
    return reset_token(outbox[-1][2])


def test_reset_changes_the_password_and_works_once(anon_client, outbox):
    username, email = active_user()
    token = ask_reset(anon_client, outbox, email)
    response = anon_client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"})
    assert response.status_code == 200
    assert login(anon_client, username).status_code == 401
    assert login(anon_client, username, "brand-new-pass-2").status_code == 200
    again = anon_client.post("/auth/reset-password", json={"token": token, "password": "third-password-3"})
    assert again.status_code == 400 and again.json()["detail"] == BAD_RESET_DETAIL
    assert outbox[-1][1] == "Your SmartIoT password was changed"  # the owner is told


def test_reset_ends_existing_sessions(anon_client, outbox):
    username, email = active_user()
    old = create_token(username, "VIEWER", now=datetime.now(timezone.utc) - timedelta(seconds=5))
    assert anon_client.get("/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 200
    token = ask_reset(anon_client, outbox, email)
    anon_client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"})
    ended = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert ended.status_code == 401 and "password was changed" in ended.json()["detail"]
    fresh = login(anon_client, username, "brand-new-pass-2").json()["access_token"]
    assert anon_client.get("/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_a_new_link_cancels_the_previous_one(anon_client, outbox):
    _, email = active_user()
    first = ask_reset(anon_client, outbox, email)
    second = ask_reset(anon_client, outbox, email)
    assert anon_client.post("/auth/reset-password", json={"token": first, "password": "brand-new-pass-2"}).status_code == 400
    assert anon_client.post("/auth/reset-password", json={"token": second, "password": "brand-new-pass-2"}).status_code == 200


def test_expired_link_is_refused(anon_client, outbox):
    username, email = active_user()
    token = ask_reset(anon_client, outbox, email)
    with SessionLocal() as session, session.begin():
        user_id = session.scalar(select(User.id).where(User.username == username))
        session.execute(update(PasswordReset).where(PasswordReset.user_id == user_id)
                        .values(expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)))
    response = anon_client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"})
    assert response.status_code == 400
    assert login(anon_client, username).status_code == 200  # password unchanged


@pytest.mark.parametrize("body, status_code", [
    ({"token": "x" * 43, "password": "brand-new-pass-2"}, 400),   # made up
    ({"token": "short", "password": "brand-new-pass-2"}, 422),
    ({"token": "x" * 43, "password": "short"}, 422),
    ({"token": "x" * 43}, 422),
])
def test_reset_validation(anon_client, body, status_code):
    assert anon_client.post("/auth/reset-password", json=body).status_code == status_code


def test_reset_unlocks_a_locked_out_account(anon_client, outbox):
    username, email = active_user()
    for _ in range(5):
        login(anon_client, username, "wrong-guess")
    assert login(anon_client, username).status_code == 429
    token = ask_reset(anon_client, outbox, email)
    anon_client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"})
    assert login(anon_client, username, "brand-new-pass-2").status_code == 200


def test_reset_link_does_not_appear_in_the_logs(anon_client, outbox, caplog):
    _, email = active_user()
    with caplog.at_level("DEBUG"):
        token = ask_reset(anon_client, outbox, email)
        anon_client.post("/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"})
    assert token not in caplog.text and "brand-new-pass-2" not in caplog.text


# ---- schema upgrade ------------------------------------------------------------------------------

def test_upgrade_adds_the_account_columns_to_an_old_database(test_users):
    """A database from Phase 18 (no email / status / password_changed_at) is upgraded in place, and its
    accounts keep working as ACTIVE."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN email, DROP COLUMN status, DROP COLUMN password_changed_at"))
    try:
        assert "_add_user_accounts" in upgrade(engine)
    finally:
        upgrade(engine)  # never leave the shared test database without the columns
    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"email", "status", "password_changed_at"} <= columns
    assert db_user(test_users["ADMIN"][0]).status == "ACTIVE"
    assert upgrade(engine) == []  # idempotent
