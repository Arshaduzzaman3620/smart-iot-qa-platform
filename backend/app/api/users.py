import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import User

from ..deps import get_db, require_role
from .. import mailer
from ..schemas import UserCreateIn, UserOut, UserUpdateIn
from ..security import hash_password

logger = logging.getLogger("backend.users")
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_role("ADMIN"))])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreateIn, tasks: BackgroundTasks, db: Session = Depends(get_db),
                admin: User = Depends(require_role("ADMIN"))):
    user = User(username=body.username, email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"User {body.username} or that email already exists")
    logger.info("User %s created with role %s by %s", user.username, user.role, admin.username)
    if user.email:
        # Never the password: the admin hands that over, or the user sets their own with "Forgot".
        tasks.add_task(mailer.send_email, user.email, "Your SmartIoT account",
                       f"Hello {user.username},\n\n{admin.username} created a SmartIoT account for you "
                       f"({user.role}).\n\nUsername: {user.username}\nSign in: {mailer.app_url()}/\n\n"
                       "Your administrator gives you the first password. To choose your own, use "
                       "\"Forgot username or password?\" on the sign-in page with this email address.\n")
    return user


@router.patch("/{username}", response_model=UserOut)
def update_user(username: str, body: UserUpdateIn, db: Session = Depends(get_db),
                admin: User = Depends(require_role("ADMIN"))):
    """Change another account's role (Phase 19). It takes effect on that user's next request."""
    if username == admin.username:
        # Same reason as for DELETE: an admin must not lock themselves out.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You cannot change your own account")
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"User {username} not found")
    user.role = body.role
    db.commit()
    logger.info("Role of %s set to %s by %s", username, user.role, admin.username)
    return user


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(username: str, db: Session = Depends(get_db), admin: User = Depends(require_role("ADMIN"))):
    if username == admin.username:
        # Otherwise the last admin could lock everyone out.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"User {username} not found")
    db.delete(user)
    db.commit()
    logger.info("User %s deleted by %s", username, admin.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
