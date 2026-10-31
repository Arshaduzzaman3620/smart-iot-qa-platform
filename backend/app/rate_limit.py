"""Slows down password guessing on POST /auth/login (Phase 15g). In memory: right for the single API
instance this project runs; several instances would need a shared store such as Redis."""

import math
import os
import threading
import time
from collections import defaultdict, deque


class LoginLimiter:
    """Counts failed logins in a sliding window, per username (from any address) and per client.

    Per username stops guessing one account's password; the price is that someone can lock a user
    out for `window` seconds by failing on purpose -- short, and logged. Per client stops one source
    spraying many usernames.
    """

    def __init__(self, per_user: int | None = None, per_client: int | None = None, window: float | None = None,
                 clock=time.monotonic):
        self.per_user = per_user if per_user is not None else int(os.getenv("LOGIN_MAX_FAILURES_PER_USER", "5"))
        self.per_client = per_client if per_client is not None else int(os.getenv("LOGIN_MAX_FAILURES_PER_CLIENT", "20"))
        self.window = window if window is not None else float(os.getenv("LOGIN_FAILURE_WINDOW", "300"))
        self._clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque:
        times = self._failures[key]
        while times and now - times[0] >= self.window:
            times.popleft()
        return times

    def retry_after(self, username: str, client: str) -> int:
        """0 if this attempt may go ahead, otherwise whole seconds until it may."""
        now = self._clock()
        with self._lock:
            waits = []
            for key, limit in ((f"user:{username.lower()}", self.per_user), (f"client:{client}", self.per_client)):
                times = self._recent(key, now)
                if len(times) >= limit:
                    waits.append(times[0] + self.window - now)
            return math.ceil(max(waits)) if waits else 0

    def failed(self, username: str, client: str):
        now = self._clock()
        with self._lock:
            if len(self._failures) > 10_000:  # bound memory: forget keys whose failures have all expired
                for key in [k for k, v in self._failures.items() if not self._recent(k, now)]:
                    del self._failures[key]
            self._failures[f"user:{username.lower()}"].append(now)
            self._failures[f"client:{client}"].append(now)

    def succeeded(self, username: str):
        """A correct password clears that user's count (not the client's)."""
        with self._lock:
            self._failures.pop(f"user:{username.lower()}", None)

    def reset(self):
        with self._lock:
            self._failures.clear()
