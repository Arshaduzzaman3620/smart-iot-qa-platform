from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

from . import config

DATABASE_URL = URL.create(
    "mysql+pymysql",
    username=config.MYSQL_USER,
    password=config.MYSQL_PASSWORD,
    host=config.MYSQL_HOST,
    port=config.MYSQL_PORT,
    database=config.MYSQL_DATABASE,
)

# pool_pre_ping: transparently replace connections MySQL has dropped (e.g. after a restart).
# Pool: up to 40 connections per process, matching the API's 40 worker threads, so a running request
# never waits for one (MySQL allows 151). If it ever does, 5 s at most: an overloaded API answers 503
# quickly instead of piling requests up (docs/testing/performance.md).
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=30, pool_timeout=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
