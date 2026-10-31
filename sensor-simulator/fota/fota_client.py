"""Simulated firmware update on the device: parse the request, download, verify, install.
No MQTT or sensor-state code here -- progress goes out through the `report` callback."""

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

FAILURE_MODES = ("none", "download", "corrupt", "install")
VERSION = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
MAX_SIZE = 1024 * 1024  # the API's upload limit
DOWNLOAD_TIMEOUT = 15


class FotaError(Exception):
    """The update can't go ahead. `update_id` is set when known, so the sensor can report FAILED."""

    def __init__(self, message: str, update_id: int | None = None):
        super().__init__(message)
        self.update_id = update_id


@dataclass
class UpdateRequest:
    update_id: int
    version: str
    size: int
    sha256: str
    url: str  # path on the API, with the download token


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_update(payload: bytes) -> UpdateRequest:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FotaError(f"not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise FotaError("update request must be a JSON object")
    update_id = data.get("update_id")
    if not _is_int(update_id) or update_id < 1:
        raise FotaError("update_id must be a positive integer")
    version, size, sha256, url = data.get("version"), data.get("size"), data.get("sha256"), data.get("url")
    if not isinstance(version, str) or not VERSION.match(version):
        raise FotaError("version must look like 1.2.3", update_id)
    if not _is_int(size) or not 0 < size <= MAX_SIZE:
        raise FotaError(f"size must be 1-{MAX_SIZE} bytes", update_id)
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise FotaError("sha256 must be 64 hex characters", update_id)
    # Only a path on our own API: an update message must not send the device to an arbitrary host.
    if not isinstance(url, str) or not url.startswith("/firmware/"):
        raise FotaError("url must be a /firmware/ path on the API", update_id)
    return UpdateRequest(update_id, version, size, sha256, url)


def download(base_url: str, path: str, max_size: int = MAX_SIZE) -> bytes:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=DOWNLOAD_TIMEOUT) as response:
            content = response.read(max_size + 1)
    except urllib.error.HTTPError as exc:
        raise FotaError(f"download failed: HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise FotaError(f"download failed: {getattr(exc, 'reason', exc)}") from None
    if len(content) > max_size:
        raise FotaError("download failed: image larger than announced limit")
    return content


def verify(content: bytes, request: UpdateRequest) -> str | None:
    """None if the image is intact, otherwise why not."""
    if len(content) != request.size:
        return f"size mismatch: got {len(content)} bytes, expected {request.size}"
    if hashlib.sha256(content).hexdigest() != request.sha256:
        return "checksum mismatch"
    return None


def run_update(request: UpdateRequest, current_version: str, battery: float, report, *, base_url: str,
               failure: str = "none", min_battery: float = 20, step_seconds: float = 1, fetch=download) -> str:
    """Do the update, calling report(status, message) at each stage. Returns the installed version.
    Raises FotaError when it can't complete; the caller reports that as FAILED."""
    if request.version == current_version:
        raise FotaError(f"already running {current_version}", request.update_id)
    if battery < min_battery:
        raise FotaError(f"battery too low ({battery:.0f} %, needs {min_battery:g} %)", request.update_id)

    report("DOWNLOADING", f"{current_version} -> {request.version}, {request.size} bytes")
    time.sleep(step_seconds)
    if failure == "download":
        raise FotaError("download failed: connection reset (injected)", request.update_id)
    try:
        content = fetch(base_url, request.url)
    except FotaError as exc:
        raise FotaError(str(exc), request.update_id) from None
    if failure == "corrupt":
        content = content[:-1] + bytes([content[-1] ^ 0xFF])  # one flipped byte

    report("VERIFYING", "checking SHA-256")
    time.sleep(step_seconds)
    problem = verify(content, request)
    if problem:
        raise FotaError(f"{problem}; staying on {current_version}", request.update_id)

    report("INSTALLING", f"writing {request.version}")
    time.sleep(step_seconds)
    if failure == "install":
        raise FotaError(f"install failed (injected); rolled back to {current_version}", request.update_id)
    return request.version
