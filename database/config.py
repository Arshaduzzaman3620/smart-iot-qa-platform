import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "smart_iot")
MYSQL_USER = os.getenv("MYSQL_USER", "smart_iot_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
