"""Password hashing and access tokens. No FastAPI or database code here, so it is unit-testable alone."""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

ROLES = ("VIEWER", "OPERATOR", "ADMIN")  # each role can do everything the ones before it can

# scrypt parameters (RFC 7914): ~16 MiB and ~50 ms per hash, so guessing is slow, logging in isn't.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SALT_BYTES = 16

TOKEN_ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "60"))


# No configured secret: a random one per process. Safe, but every restart signs everyone out.
# (Warned about at API startup, once logging is set up.)
JWT_SECRET_CONFIGURED = bool(os.getenv("JWT_SECRET"))
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)


def role_allows(role: str, required: str) -> bool:
    """True if `role` is `required` or higher. Unknown roles are allowed nothing."""
    return role in ROLES and ROLES.index(role) >= ROLES.index(required)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024, dklen=32)


def hash_password(password: str) -> str:
    """'scrypt$n$r$p$salt$hash' -- the parameters are stored so they can be raised later."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, base64.b64decode(digest))


# Checked against when the username doesn't exist, so a wrong username takes as long as a wrong
# password and response times don't reveal which usernames exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def create_token(username: str, role: str, minutes: int = TOKEN_MINUTES, now: datetime | None = None) -> str:
    issued = now or datetime.now(timezone.utc)
    claims = {"sub": username, "role": role, "iat": issued, "exp": issued + timedelta(minutes=minutes)}
    return jwt.encode(claims, JWT_SECRET, algorithm=TOKEN_ALGORITHM)


DOWNLOAD_SCOPE = "firmware:download"
DOWNLOAD_TOKEN_MINUTES = 10


def create_download_token(firmware_id: int, sensor_id: str, minutes: int = DOWNLOAD_TOKEN_MINUTES,
                          now: datetime | None = None) -> str:
    """Lets one sensor download one firmware image for a few minutes -- sensors have no user account."""
    issued = now or datetime.now(timezone.utc)
    claims = {"sub": sensor_id, "scope": DOWNLOAD_SCOPE, "fw": firmware_id, "iat": issued,
              "exp": issued + timedelta(minutes=minutes)}
    return jwt.encode(claims, JWT_SECRET, algorithm=TOKEN_ALGORITHM)


def decode_token(token: str) -> dict:
    """The token's claims. Raises jwt.InvalidTokenError if it is malformed, tampered with or expired."""
    # `algorithms` pinned: never accept "none" or an algorithm the client picked.
    return jwt.decode(token, JWT_SECRET, algorithms=[TOKEN_ALGORITHM], options={"require": ["sub", "exp"]})
