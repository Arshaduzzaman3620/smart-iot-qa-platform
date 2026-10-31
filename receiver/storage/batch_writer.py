import logging
import queue
import threading
import time
from collections.abc import Callable

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from storage.telemetry_repository import SaveResult, TelemetryRepository

logger = logging.getLogger("receiver.writer")

_STOP = object()

# MySQL client errors meaning "can't reach the server", not "this message is bad": can't connect,
# server gone away, lost connection during query, lost connection at handshake.
OUTAGE_CODES = {2003, 2006, 2013, 2055}
RETRY_MIN, RETRY_MAX = 1.0, 10.0  # seconds between attempts while the database is down


def is_outage(exc: Exception) -> bool:
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return True
    orig = getattr(exc, "orig", None)
    code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
    return code in OUTAGE_CODES


class BatchWriter:
    """Stores validated messages from a queue on one writer thread, many per transaction.

    The MQTT callback only parses, validates and submits, so a slow database never blocks the
    network loop. The writer takes whatever is waiting (up to `max_batch`) and saves it with one
    commit: at low load a batch is a single message (no added latency); under load batches grow
    and the commit cost is shared. One thread keeps every sensor's messages in arrival order.
    """

    def __init__(
        self,
        repository: TelemetryRepository,
        on_saved: Callable[[dict, SaveResult], None],
        on_failed: Callable[[dict, Exception], None],
        max_batch: int = 200,
        max_queue: int = 10_000,
    ):
        self._repository = repository
        self._on_saved = on_saved
        self._on_failed = on_failed
        self._max_batch = max_batch
        # Bounded: if the database falls far behind, submit() blocks the MQTT thread, and the
        # broker holds further messages instead of this process growing without limit.
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(target=self._run, name="batch-writer", daemon=True)
        self._stopping = threading.Event()
        # Outage state, read by the receiver's offline check (main.py): while the database is down,
        # or its backlog is still being stored, last_seen is stale for every sensor.
        self.in_outage = False
        self.outage_ended_at: float | None = None  # time.monotonic()

    @property
    def backlog(self) -> int:
        return self._queue.qsize()

    def start(self):
        self._thread.start()

    def submit(self, data: dict, on_done: Callable[[], None] | None = None):
        """Queue `data` for storing. `on_done()` runs once it is stored or definitively rejected -- the
        receiver acknowledges the MQTT message there, so a crash before that means redelivery, not loss.
        It does not run when the database was still unreachable at shutdown: the broker redelivers."""
        self._queue.put((data, on_done))

    def stop(self, timeout: float = 30) -> bool:
        """Store everything already submitted, then stop. Returns False if that took too long."""
        self._stopping.set()
        self._queue.put(_STOP)
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self):
        stopping = False
        while not stopping:
            item = self._queue.get()
            if item is _STOP:
                break
            batch = [item]
            while len(batch) < self._max_batch:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is _STOP:
                    stopping = True
                    break
                batch.append(item)
            try:
                self._write(batch)
            except Exception:
                # Never let an unexpected error kill the only writer thread.
                logger.exception("Unexpected error storing a batch of %d message(s)", len(batch))

    def _write(self, batch: list[tuple]):
        messages = [data for data, _ in batch]
        try:
            results = self._save_through_outage(messages)
        except SQLAlchemyError as exc:
            if len(batch) == 1:
                self._failed(batch[0], exc)
                return
            # The whole transaction rolled back. Retry one by one, so a single message the database
            # rejects (or a deadlock) costs only that message, not the whole batch.
            logger.warning("Batch of %d failed (%s); retrying one by one", len(batch), getattr(exc, "orig", exc))
            for item in batch:
                try:
                    result = self._repository.save(item[0])
                except SQLAlchemyError as single_exc:
                    self._failed(item, single_exc)
                else:
                    self._saved(item, result)
            return
        if len(batch) > 1:
            logger.debug("Stored a batch of %d messages", len(batch))
        for item, result in zip(batch, results):
            self._saved(item, result)

    def _saved(self, item: tuple, result: SaveResult):
        data, on_done = item
        try:
            self._on_saved(data, result)
        finally:
            if on_done:
                on_done()

    def _failed(self, item: tuple, exc: Exception):
        data, on_done = item
        try:
            self._on_failed(data, exc)
        finally:
            # Rejected by the database: acknowledge, redelivering it would fail the same way. Still
            # unreachable (only at shutdown): don't, so the broker delivers it again next time.
            if on_done and not is_outage(exc):
                on_done()

    def _save_through_outage(self, batch: list[dict]):
        """save_batch, but while the database is unreachable keep the batch and retry with backoff,
        instead of dropping it. Messages arriving meanwhile wait in the queue (and, once that is full,
        at the broker -- the receiver has a persistent session). Other errors are raised as before."""
        delay, started = RETRY_MIN, None
        while True:
            try:
                results = self._repository.save_batch(batch)
            except SQLAlchemyError as exc:
                if not is_outage(exc) or (self._stopping.is_set() and started is not None
                                          and time.monotonic() - started > RETRY_MAX):
                    raise
                if started is None:
                    started = time.monotonic()
                    self.in_outage = True
                    logger.error("Database unreachable (%s); holding %d message(s), retrying",
                                 getattr(exc, "orig", exc), len(batch) + self.backlog)
                time.sleep(delay)
                delay = min(delay * 2, RETRY_MAX)
                continue
            if started is not None:
                self.in_outage = False
                self.outage_ended_at = time.monotonic()
                logger.warning("Database back after %.1f s; storing %d held message(s)",
                               time.monotonic() - started, len(batch) + self.backlog)
            return results
