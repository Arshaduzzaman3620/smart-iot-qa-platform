from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User
from database.session import SessionLocal

from .security import decode_token, role_allows


def get_db() -> Iterator[Session]:
    """One session per request, always closed afterwards."""
    with SessionLocal() as session:
        yield session


_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        claims = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")
    if "scope" in claims:
        # A firmware download token is not a login: it must never open the rest of the API.
        raise _unauthorized("Invalid token")
    # The user is looked up on every request, so deleting a user or changing their role takes
    # effect at once instead of when their token expires.
    user = db.scalar(select(User).where(User.username == claims["sub"]))
    if user is None:
        raise _unauthorized("Invalid token")
    return user


def require_role(required: str):
    """Dependency: the current user, if their role is `required` or higher; otherwise 403."""

    def check(user: User = Depends(get_current_user)) -> User:
        if not role_allows(user.role, required):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Requires role {required} or higher")
        return user

    return check
