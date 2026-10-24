from collections.abc import Iterator

from sqlalchemy.orm import Session

from database.session import SessionLocal


def get_db() -> Iterator[Session]:
    """One session per request, always closed afterwards."""
    with SessionLocal() as session:
        yield session
