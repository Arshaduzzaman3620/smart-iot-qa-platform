import sys

# The models use `str | None` annotations, which SQLAlchemy evaluates at import time. On an older
# Python that fails with a confusing TypeError deep inside SQLAlchemy, so say what is wrong instead.
if sys.version_info < (3, 10):
    raise SystemExit(f"Python 3.10+ is required (3.12 recommended), this is {sys.version.split()[0]}. "
                     "See docs/development/setup.md, or run everything in Docker: docker compose up -d --build")
