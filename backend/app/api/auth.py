import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User

from ..deps import get_current_user, get_db
from ..schemas import LoginIn, TokenOut, UserOut
from ..security import DUMMY_HASH, TOKEN_MINUTES, create_token, verify_password

logger = logging.getLogger("backend.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    # Always run one hash check, so unknown usernames aren't faster to reject than wrong passwords.
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        logger.warning("Failed login for username %r", body.username)  # never log the password
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    logger.info("User %s logged in (%s)", user.username, user.role)
    return TokenOut(access_token=create_token(user.username, user.role), expires_in=TOKEN_MINUTES * 60,
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
