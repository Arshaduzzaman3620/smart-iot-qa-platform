"""The first admin account, so a fresh install can be signed into at all."""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database.models import User

from .security import hash_password

logger = logging.getLogger("backend.bootstrap")


def ensure_admin(session_factory, username: str, password: str) -> bool:
    """Create `username` as ADMIN if there are no users at all. True if it was created.

    Only ever on an empty users table: once anyone exists, accounts are managed through the API,
    and changing ADMIN_PASSWORD later does not reset anybody's password.
    """
    if not password:
        logger.warning("ADMIN_PASSWORD not set: no initial admin is created")
        return False
    try:
        with session_factory() as session, session.begin():
            if session.scalar(select(func.count()).select_from(User)):
                return False
            session.add(User(username=username, password_hash=hash_password(password), role="ADMIN"))
    except IntegrityError:
        return False  # another API instance created it at the same moment
    except SQLAlchemyError as exc:
        # The API still starts (and serves 503s) while MySQL is down; the next start retries.
        logger.error("Could not create the initial admin: %s", getattr(exc, "orig", exc))
        return False
    logger.info("Created initial admin user %s", username)
    return True
