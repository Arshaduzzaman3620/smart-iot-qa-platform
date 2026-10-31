import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import PasswordReset, User

from .. import mailer
from ..deps import get_current_user, get_db
from ..rate_limit import LoginLimiter
from ..schemas import ForgotIn, LoginIn, MessageOut, RegisterIn, ResetIn, TokenOut, UserOut
from ..security import DUMMY_HASH, TOKEN_MINUTES, create_token, hash_password, verify_password

logger = logging.getLogger("backend.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
limiter = LoginLimiter()
# Phase 19. Each request counts (not only failures), so they cap how often someone can sign up or ask
# for reset emails: per email address and per client, within an hour.
signup_limiter = LoginLimiter(per_user=3, per_client=10, window=3600)
forgot_limiter = LoginLimiter(per_user=3, per_client=10, window=3600)

RESET_MINUTES = int(os.getenv("RESET_MINUTES", "30"))
PENDING_DETAIL = "Your account is waiting for an administrator's approval"
FORGOT_DETAIL = "If that email belongs to an account, we have sent the username and a reset link to it."
BAD_RESET_DETAIL = "This reset link is invalid or has expired. Ask for a new one."


def utcnow() -> datetime:
    """Naive UTC, whole seconds: what MySQL DATETIME stores (it would round fractions up)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _too_many(limiter_: LoginLimiter, key: str, client: str):
    wait = limiter_.retry_after(key, client)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests, try again later",
                            headers={"Retry-After": str(wait)})
    limiter_.failed(key, client)


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
    if user.status != "ACTIVE":
        # Only after the password matched, so this doesn't reveal which usernames exist.
        logger.info("Login for %s refused: account %s", user.username, user.status)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=PENDING_DETAIL)
    logger.info("User %s logged in (%s)", user.username, user.role)
    return TokenOut(access_token=create_token(user.username, user.role), expires_in=TOKEN_MINUTES * 60,
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_201_CREATED,
             responses={409: {"description": "Username or email already in use"}, 429: {"description": "Too many"}})
def register(body: RegisterIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Ask for an account. It starts as a PENDING VIEWER: no sign-in until an admin approves it."""
    _too_many(signup_limiter, body.email, client_address(request))
    user = User(username=body.username, email=body.email, password_hash=hash_password(body.password),
                role="VIEWER", status="PENDING")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username or email already in use")
    logger.info("Sign-up: %s (%s) waiting for approval", user.username, user.email)
    admins = db.scalars(select(User.email).where(User.role == "ADMIN", User.status == "ACTIVE",
                                                 User.email.is_not(None))).all()
    for address in admins:
        tasks.add_task(mailer.send_email, address, f"SmartIoT: {user.username} is waiting for approval",
                       f"{user.username} ({user.email}) asked for an account.\n\n"
                       f"Approve or reject it in Users: {mailer.app_url()}/#users\n")
    return MessageOut(detail="Account created. An administrator must approve it before you can sign in.")


@router.post("/forgot-password", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED,
             responses={429: {"description": "Too many"}})
def forgot_password(body: ForgotIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Email the username and a one-time reset link. The answer is the same whether or not the address
    has an account, and the email goes out in the background, so neither text nor timing tells."""
    _too_many(forgot_limiter, body.email, client_address(request))
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or user.status != "ACTIVE":
        logger.info("Password reset asked for an address without an active account")
        return MessageOut(detail=FORGOT_DETAIL)
    now = utcnow()
    # One valid link at a time: asking again cancels the previous one.
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
               .values(used_at=now))
    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=token_hash(token),
                         expires_at=now + timedelta(minutes=RESET_MINUTES)))
    db.commit()
    logger.info("Password reset link issued for %s", user.username)
    tasks.add_task(mailer.send_email, user.email, "Your SmartIoT username and password reset",
                   f"Hello {user.username},\n\n"
                   f"Your username is: {user.username}\n\n"
                   f"To choose a new password, open this link within {RESET_MINUTES} minutes:\n"
                   f"{mailer.app_url()}/?reset={token}\n\n"
                   "The link works once. If you didn't ask for this, ignore this email: nothing changes.\n")
    return MessageOut(detail=FORGOT_DETAIL)


@router.post("/reset-password", response_model=MessageOut, responses={400: {"description": "Invalid or expired link"}})
def reset_password(body: ResetIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Set a new password with a link from /forgot-password. Every existing session of the user ends."""
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_hash(body.token)))
    now = utcnow()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=BAD_RESET_DETAIL)
    user = db.get(User, reset.user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=BAD_RESET_DETAIL)
    user.password_hash = hash_password(body.password)
    user.password_changed_at = now
    reset.used_at = now
    db.commit()
    limiter.succeeded(user.username)  # a locked-out user is let back in
    logger.info("Password reset for %s", user.username)
    tasks.add_task(mailer.send_email, user.email, "Your SmartIoT password was changed",
                   f"Hello {user.username},\n\nYour password was just changed and every signed-in session "
                   "was ended. If this wasn't you, contact your administrator at once.\n")
    return MessageOut(detail="Password changed. You can sign in now.")
