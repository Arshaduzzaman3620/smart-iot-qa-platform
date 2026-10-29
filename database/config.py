import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Defaults reach the MySQL container that compose.yaml publishes on the host, so Python run on the
# host needs no .env. Containers set MYSQL_HOST=mysql / MYSQL_PORT=3306 themselves (environment
# variables win over .env).
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "smart_iot")
MYSQL_USER = os.getenv("MYSQL_USER", "smart_iot_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "changeme")
