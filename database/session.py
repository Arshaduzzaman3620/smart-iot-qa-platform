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
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
