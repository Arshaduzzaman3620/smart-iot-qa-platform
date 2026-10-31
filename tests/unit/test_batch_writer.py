"""BatchWriter with a fake repository: batching, ordering, failure isolation, draining on stop."""

import threading

import pytest
from sqlalchemy.exc import OperationalError

from storage.batch_writer import BatchWriter
from storage.telemetry_repository import SaveResult


def db_error():
    return OperationalError("INSERT ...", {}, Exception("Data too long for column 'sensor_id'"))


class FakeRepository:
    def __init__(self, bad_ids=(), gate: threading.Event | None = None):
        self.batches: list[list[str]] = []
        self.bad_ids = set(bad_ids)
        self.gate = gate  # when set, save_batch waits for it (to let messages queue up)

    def save_batch(self, batch):
        if self.gate:
            self.gate.wait(5)
        self.batches.append([d["id"] for d in batch])
        if any(d["id"] in self.bad_ids for d in batch):
            raise db_error()
        return [SaveResult(telemetry_id=d["id"]) for d in batch]

    def save(self, data):
        return self.save_batch([data])[0]


class Recorder:
    def __init__(self):
        self.saved, self.failed = [], []

    def on_saved(self, data, result):
        assert result.telemetry_id == data["id"]
        self.saved.append(data["id"])

    def on_failed(self, data, exc):
        self.failed.append(data["id"])


def run(repo, ids, max_batch=200, recorder=None):
    """Queue all messages before the writer starts, so they are waiting together; then drain."""
    recorder = recorder or Recorder()
    writer = BatchWriter(repo, recorder.on_saved, recorder.on_failed, max_batch=max_batch)
    for i in ids:
        writer.submit({"id": i})
    writer.start()
    assert writer.stop(timeout=5)
    return recorder


def test_waiting_messages_are_stored_in_one_batch():
    repo = FakeRepository()
    recorder = run(repo, range(5))
    assert repo.batches == [[0, 1, 2, 3, 4]]
    assert recorder.saved == [0, 1, 2, 3, 4]


def test_batch_size_is_capped_and_order_kept():
    repo = FakeRepository()
    recorder = run(repo, range(450), max_batch=200)
    assert [len(b) for b in repo.batches] == [200, 200, 50]
    assert recorder.saved == list(range(450))


def test_single_message_is_written_immediately_without_waiting_for_more():
    repo = FakeRepository()
    recorder = Recorder()
    writer = BatchWriter(repo, recorder.on_saved, recorder.on_failed)
    writer.start()
    writer.submit({"id": 1})
    for _ in range(100):
        if recorder.saved:
            break
        threading.Event().wait(0.01)
    assert recorder.saved == [1]
    assert writer.stop()


def test_messages_arriving_during_a_write_form_the_next_batch():
    gate = threading.Event()
    repo = FakeRepository(gate=gate)
    recorder = Recorder()
    writer = BatchWriter(repo, recorder.on_saved, recorder.on_failed)
    writer.start()
    writer.submit({"id": 0})       # picked up alone; the write blocks on the gate
    threading.Event().wait(0.1)
    for i in range(1, 4):
        writer.submit({"id": i})   # queue up behind it
    gate.set()
    assert writer.stop()
    assert repo.batches == [[0], [1, 2, 3]]


def test_failed_batch_is_retried_one_by_one_so_only_the_bad_message_is_lost():
    repo = FakeRepository(bad_ids={2})
    recorder = run(repo, range(5))
    assert recorder.saved == [0, 1, 3, 4]
    assert recorder.failed == [2]
    assert repo.batches[0] == [0, 1, 2, 3, 4]          # the batch attempt
    assert repo.batches[1:] == [[0], [1], [2], [3], [4]]  # then one by one


def test_single_failed_message_is_not_retried():
    repo = FakeRepository(bad_ids={7})
    recorder = run(repo, [7])
    assert recorder.failed == [7]
    assert repo.batches == [[7]]


def test_database_down_fails_every_message_but_writer_keeps_running():
    repo = FakeRepository(bad_ids=set(range(3)))
    recorder = run(repo, range(3))
    assert recorder.failed == [0, 1, 2]
    assert recorder.saved == []


def test_writer_survives_callback_error_and_processes_later_messages(caplog):
    repo = FakeRepository()
    seen = []

    def on_saved(data, result):
        seen.append(data["id"])
        if data["id"] == 0:
            raise RuntimeError("bug in a callback")

    writer = BatchWriter(repo, on_saved, lambda d, e: None)
    writer.start()
    writer.submit({"id": 0})
    for _ in range(100):
        if seen:
            break
        threading.Event().wait(0.01)
    writer.submit({"id": 1})
    assert writer.stop()
    assert seen == [0, 1]
    assert "Unexpected error storing a batch" in caplog.text


def test_stop_stores_everything_submitted_first():
    gate = threading.Event()
    repo = FakeRepository(gate=gate)
    recorder = Recorder()
    writer = BatchWriter(repo, recorder.on_saved, recorder.on_failed, max_batch=10)
    writer.start()
    for i in range(25):
        writer.submit({"id": i})
    stopper = threading.Thread(target=writer.stop)
    stopper.start()
    gate.set()
    stopper.join(5)
    assert recorder.saved == list(range(25))


@pytest.mark.parametrize("max_batch", [1, 3])
def test_small_batch_sizes(max_batch):
    repo = FakeRepository()
    recorder = run(repo, range(7), max_batch=max_batch)
    assert recorder.saved == list(range(7))
    assert max(len(b) for b in repo.batches) == max_batch


# ---- database outages and acknowledgements (Phase 15f) -----------------------------------------

def outage_error(code=2013):
    from pymysql.err import OperationalError as PyMySQLError
    return OperationalError("INSERT ...", {}, PyMySQLError(code, "Lost connection to MySQL server"))


class FlakyRepository(FakeRepository):
    """Unreachable for the first `down_for` attempts, then fine."""

    def __init__(self, down_for: int):
        super().__init__()
        self.down_for, self.attempts = down_for, 0

    def save_batch(self, batch):
        self.attempts += 1
        if self.attempts <= self.down_for:
            raise outage_error()
        return super().save_batch(batch)


@pytest.fixture
def no_backoff(monkeypatch):
    import storage.batch_writer as module
    monkeypatch.setattr(module, "RETRY_MIN", 0.01)
    monkeypatch.setattr(module, "RETRY_MAX", 0.02)


@pytest.mark.parametrize("code", [2003, 2006, 2013, 2055])
def test_connection_errors_count_as_an_outage(code):
    from storage.batch_writer import is_outage
    assert is_outage(outage_error(code))


def test_data_errors_are_not_an_outage():
    from storage.batch_writer import is_outage
    assert not is_outage(db_error())


def test_outage_holds_the_batch_and_stores_it_when_back(no_backoff):
    from helpers import wait_until

    repo, recorder = FlakyRepository(down_for=3), Recorder()
    writer = BatchWriter(repo, recorder.on_saved, recorder.on_failed)
    for i in (1, 2, 3):
        writer.submit({"id": i})
    writer.start()
    wait_until(lambda: len(recorder.saved) == 3, timeout=5)  # not stopping: stop() limits the waiting
    assert writer.stop()
    assert recorder.saved == [1, 2, 3] and recorder.failed == []
    assert repo.attempts == 4  # three refused, then stored -- the batch was never split or dropped


def test_outage_state_is_visible_while_down(no_backoff):
    gate, seen = threading.Event(), []

    class Watched(FlakyRepository):
        def save_batch(self, batch):
            seen.append(writer.in_outage)
            return super().save_batch(batch)

    recorder = Recorder()
    writer = BatchWriter(Watched(down_for=2), recorder.on_saved, recorder.on_failed)
    writer.submit({"id": 1})
    writer.start()
    assert writer.stop()
    assert seen == [False, True, True]
    assert writer.in_outage is False and writer.outage_ended_at is not None


def test_ack_runs_after_storing():
    order = []
    recorder = Recorder()
    recorder.on_saved = lambda data, result: order.append(("stored", data["id"]))
    writer = BatchWriter(FakeRepository(), recorder.on_saved, recorder.on_failed)
    for i in (1, 2):
        writer.submit({"id": i}, on_done=lambda i=i: order.append(("acked", i)))
    writer.start()
    assert writer.stop()
    assert order == [("stored", 1), ("acked", 1), ("stored", 2), ("acked", 2)]


def test_rejected_message_is_acked_so_it_is_not_redelivered():
    acked = []
    recorder = Recorder()
    writer = BatchWriter(FakeRepository(bad_ids={2}), recorder.on_saved, recorder.on_failed)
    for i in (1, 2, 3):
        writer.submit({"id": i}, on_done=lambda i=i: acked.append(i))
    writer.start()
    assert writer.stop()
    assert recorder.failed == [2]
    assert acked == [1, 2, 3]


def test_unreachable_at_shutdown_is_not_acked_so_the_broker_redelivers(no_backoff):
    acked = []
    recorder = Recorder()
    writer = BatchWriter(FlakyRepository(down_for=10_000), recorder.on_saved, recorder.on_failed)
    writer.submit({"id": 1}, on_done=lambda: acked.append(1))
    writer.start()
    assert writer.stop(timeout=10)
    assert recorder.failed == [1]
    assert acked == []
