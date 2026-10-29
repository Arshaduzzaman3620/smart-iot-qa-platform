"""Password hashing, tokens and the role ladder (backend/app/security.py)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.app import security
from backend.app.security import ROLES, create_token, decode_token, hash_password, role_allows, verify_password

# 32+ bytes, so PyJWT does not warn; it is still the wrong key.
WRONG_KEY = "guessed-secret-that-is-long-enough-for-hs256"



def test_hash_verifies_only_the_right_password():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("correct horsE", stored)
    assert not verify_password("", stored)


def test_same_password_hashes_differently_each_time():
    # Random salt: equal passwords can't be spotted in the users table.
    assert hash_password("same") != hash_password("same")


def test_hash_never_contains_the_password():
    assert "hunter2" not in hash_password("hunter2")


@pytest.mark.parametrize("stored", ["", "plain", "md5$abc", "scrypt$x$8$1$AAAA$AAAA", "scrypt$1$2$3"])
def test_malformed_stored_hash_is_a_failed_check_not_a_crash(stored):
    assert verify_password("anything", stored) is False


def test_unicode_password():
    stored = hash_password("pässwörd-密码")
    assert verify_password("pässwörd-密码", stored)


@pytest.mark.parametrize("role, required, allowed", [
    ("VIEWER", "VIEWER", True), ("VIEWER", "OPERATOR", False), ("VIEWER", "ADMIN", False),
    ("OPERATOR", "VIEWER", True), ("OPERATOR", "OPERATOR", True), ("OPERATOR", "ADMIN", False),
    ("ADMIN", "VIEWER", True), ("ADMIN", "OPERATOR", True), ("ADMIN", "ADMIN", True),
    ("viewer", "VIEWER", False), ("ROOT", "VIEWER", False), ("", "VIEWER", False),
])
def test_role_ladder(role, required, allowed):
    assert role_allows(role, required) is allowed


def test_roles_are_ordered_least_to_most_privileged():
    assert ROLES == ("VIEWER", "OPERATOR", "ADMIN")


def test_token_round_trip():
    claims = decode_token(create_token("alice", "OPERATOR"))
    assert claims["sub"] == "alice"
    assert claims["role"] == "OPERATOR"


def test_expired_token_is_rejected():
    issued = datetime.now(timezone.utc) - timedelta(minutes=61)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(create_token("alice", "VIEWER", minutes=60, now=issued))


def test_token_still_valid_just_before_expiry():
    issued = datetime.now(timezone.utc) - timedelta(minutes=59)
    assert decode_token(create_token("alice", "VIEWER", minutes=60, now=issued))["sub"] == "alice"


def test_tampered_token_is_rejected():
    header, payload, signature = create_token("alice", "VIEWER").split(".")
    forged = jwt.encode({"sub": "alice", "role": "ADMIN", "exp": 9999999999}, WRONG_KEY, algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(f"{header}.{forged.split('.')[1]}.{signature}")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(forged)


def test_alg_none_token_is_rejected():
    unsigned = jwt.encode({"sub": "alice", "role": "ADMIN", "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(unsigned)


def test_token_without_expiry_is_rejected():
    endless = jwt.encode({"sub": "alice", "role": "ADMIN"}, security.JWT_SECRET, algorithm="HS256")
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(endless)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_token_is_rejected(garbage):
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(garbage)
