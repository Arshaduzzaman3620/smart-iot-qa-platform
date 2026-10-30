import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User

from ..deps import get_current_user, get_db
from ..rate_limit import LoginLimiter
from ..schemas import LoginIn, TokenOut, UserOut
from ..security import DUMMY_HASH, TOKEN_MINUTES, create_token, verify_password

logger = logging.getLogger("backend.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
limiter = LoginLimiter()


def client_address(request: Request) -> str:
    # Behind the dashboard's nginx every request comes from nginx, so with TRUST_PROXY=1 (set in
    # Compose) the address nginx saw is used. Not trusted by default: anyone can send that header.
    if os.getenv("TRUST_PROXY") == "1" and request.headers.get("x-real-ip"):
        return request.headers["x-real-ip"]
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenOut, responses={429: {"description": "Too many failed attempts"}})
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    client = client_address(request)
    wait = limiter.retry_after(body.username, client)
    if wait:
        logger.warning("Login for %r from %s refused: too many failed attempts", body.username, client)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts, try again later",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.username == body.username))
    # Always run one hash check, so unknown usernames aren't faster to reject than wrong passwords.
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        limiter.failed(body.username, client)
        logger.warning("Failed login for username %r from %s", body.username, client)  # never log the password
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    limiter.succeeded(body.username)
    logger.info("User %s logged in (%s)", user.username, user.role)
    return TokenOut(access_token=create_token(user.username, user.role), expires_in=TOKEN_MINUTES * 60,
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
