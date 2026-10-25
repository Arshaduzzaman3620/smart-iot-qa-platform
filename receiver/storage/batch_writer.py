import logging
import queue
import threading
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError

from storage.telemetry_repository import SaveResult, TelemetryRepository

logger = logging.getLogger("receiver.writer")

_STOP = object()


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

    def start(self):
        self._thread.start()

    def submit(self, data: dict):
        self._queue.put(data)

    def stop(self, timeout: float = 30) -> bool:
        """Store everything already submitted, then stop. Returns False if that took too long."""
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

    def _write(self, batch: list[dict]):
        try:
            results = self._repository.save_batch(batch)
        except SQLAlchemyError as exc:
            if len(batch) == 1:
                self._on_failed(batch[0], exc)
                return
            # The whole transaction rolled back. Retry one by one, so a single message the database
            # rejects (or a deadlock) costs only that message, not the whole batch.
            logger.warning("Batch of %d failed (%s); retrying one by one", len(batch), getattr(exc, "orig", exc))
            for data in batch:
                try:
                    result = self._repository.save(data)
                except SQLAlchemyError as single_exc:
                    self._on_failed(data, single_exc)
                else:
                    self._on_saved(data, result)
            return
        if len(batch) > 1:
            logger.debug("Stored a batch of %d messages", len(batch))
        for data, result in zip(batch, results):
            self._on_saved(data, result)
