"""init_db_when_ready: retry while MySQL is still starting, fail at once on anything else."""

import pytest
from pymysql.err import OperationalError as PyMySQLError
from sqlalchemy.exc import OperationalError

from database import init_db as module


def db_error(code: int) -> OperationalError:
    return OperationalError("SELECT 1", {}, PyMySQLError(code, "mysql says no"))


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


def fail_then_succeed(monkeypatch, errors):
    """init_db raises each of `errors` in turn, then returns the table list."""
    calls = []

    def fake_init_db():
        calls.append(1)
        if errors:
            raise errors.pop(0)
        return ["alerts", "sensors", "telemetry"]

    monkeypatch.setattr(module, "init_db", fake_init_db)
    return calls


@pytest.mark.parametrize("code", [2003, 2013])
def test_retries_until_mysql_accepts_connections(monkeypatch, fake_time, code):
    calls = fail_then_succeed(monkeypatch, [db_error(code), db_error(code)])
    tables = module.init_db_when_ready(60, sleep=fake_time.sleep, clock=fake_time.clock)
    assert tables == ["alerts", "sensors", "telemetry"]
    assert len(calls) == 3
    assert fake_time.sleeps == [module.RETRY_INTERVAL] * 2


def test_no_wait_fails_on_first_refusal(monkeypatch, fake_time):
    # Default for host runs: a clear error at once, as before (Phase 8 behavior).
    calls = fail_then_succeed(monkeypatch, [db_error(2003)])
    with pytest.raises(OperationalError):
        module.init_db_when_ready(0, sleep=fake_time.sleep, clock=fake_time.clock)
    assert len(calls) == 1
    assert fake_time.sleeps == []


def test_gives_up_when_wait_runs_out(monkeypatch, fake_time):
    calls = fail_then_succeed(monkeypatch, [db_error(2003)] * 100)
    with pytest.raises(OperationalError):
        module.init_db_when_ready(10, sleep=fake_time.sleep, clock=fake_time.clock)
    assert fake_time.now <= 10
    assert len(calls) == 10 // module.RETRY_INTERVAL + 1


@pytest.mark.parametrize("code", [1045, 1049])  # access denied, unknown database
def test_errors_that_wont_fix_themselves_fail_at_once(monkeypatch, fake_time, code):
    calls = fail_then_succeed(monkeypatch, [db_error(code)])
    with pytest.raises(OperationalError):
        module.init_db_when_ready(60, sleep=fake_time.sleep, clock=fake_time.clock)
    assert len(calls) == 1
