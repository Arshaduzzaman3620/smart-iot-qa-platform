"""Start (or reuse) the FastAPI and Vite dev servers for browser tests."""

import os
import subprocess
import sys

import pytest

from helpers import ROOT, port_open, wait_until

API_PORT = int(os.getenv("API_PORT", "8000"))
DASHBOARD_PORT = 5173
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"


def _stop(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # npx/uvicorn spawn children; kill the whole tree or the port stays taken.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
    process.wait(timeout=10)


def _serve(name: str, port: int, command: list[str], cwd, log_dir):
    """Yield once `port` is serving. Reuses a server that is already running (e.g. your own dev server)."""
    if port_open("localhost", port):
        yield
        return
    log_path = log_dir / f"{name}.log"
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                   env={**os.environ, "PYTHONUNBUFFERED": "1"})
        try:
            wait_until(lambda: port_open("localhost", port) or process.poll() is not None, timeout=60)
            if process.poll() is not None:
                pytest.fail(f"{name} exited early:\n{log_path.read_text(encoding='utf-8')}")
            yield
        finally:
            _stop(process)


@pytest.fixture(scope="session")
def dashboard_server(tmp_path_factory):
    if not (ROOT / "frontend" / "node_modules").exists():
        pytest.skip("frontend dependencies not installed (run npm install in frontend/)")
    npx = "npx.cmd" if os.name == "nt" else "npx"
    yield from _serve("vite", DASHBOARD_PORT, [npx, "vite", "--port", str(DASHBOARD_PORT), "--strictPort"],
                      ROOT / "frontend", tmp_path_factory.mktemp("vite"))


@pytest.fixture(scope="session")
def api_server(mysql_available, tmp_path_factory):
    yield from _serve("api", API_PORT, [sys.executable, "-m", "backend.app.main"], ROOT,
                      tmp_path_factory.mktemp("api"))
