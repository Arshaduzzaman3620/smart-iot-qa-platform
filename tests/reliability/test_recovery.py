"""Outages and crashes while sensors keep reporting (Phase 15f). Each scenario checks the two things
that matter: nothing is lost, nothing is stored twice -- and measures how long recovery takes.
Run `pytest tests/reliability -s` to see the measurements."""

import time

from helpers import report

OUTAGE_SECONDS = 10


def test_mysql_outage_holds_messages_and_stores_them_after(harness):
    # OFFLINE_TIMEOUT shorter than the outage: sensors must still not be flagged OFFLINE afterwards.
    harness.start_receiver(OFFLINE_TIMEOUT="5", OFFLINE_STARTUP_GRACE="5")
    harness.start_simulator(count=5, interval=1)
    time.sleep(3)

    harness.mysql.cut()
    time.sleep(OUTAGE_SECONDS)
    assert "Database unreachable" in harness.log("receiver")
    held_at_restore = len(harness.sent()) - len(harness.stored())
    harness.mysql.restore()
    restored = time.monotonic()

    harness.wait_until_all_stored(timeout=60)
    recovery = time.monotonic() - restored
    harness.stop_simulator()
    harness.wait_until_all_stored(timeout=30)
    total = harness.assert_no_loss_no_duplicates()
    assert "Database back after" in harness.log("receiver")
    assert harness.offline_alerts() == 0, [l for l in harness.log("receiver").splitlines() if "OFFLINE" in l]
    assert recovery < 20
    report("mysql outage", outage_s=OUTAGE_SECONDS, held=held_at_restore, readings=total,
           backlog_stored_s=round(recovery, 1), lost=0, duplicates=0)


def test_broker_unreachable_for_sensors_they_buffer_and_resend(harness):
    harness.start_receiver()
    harness.start_simulator(count=5, interval=1)
    time.sleep(3)

    harness.broker.cut()
    time.sleep(OUTAGE_SECONDS)
    buffered = harness.log("simulator").count("Telemetry buffered")
    assert buffered >= 5 * (OUTAGE_SECONDS - 2)
    harness.broker.restore()
    restored = time.monotonic()

    harness.wait_until_all_stored(timeout=60)  # includes every buffered reading
    recovery = time.monotonic() - restored
    # Readings keep being buffered until the sensor has actually reconnected, so compare totals.
    log = harness.log("simulator")
    buffered = log.count("Telemetry buffered")
    assert log.count("(was buffered") == buffered
    harness.stop_simulator()
    harness.wait_until_all_stored(timeout=30)
    total = harness.assert_no_loss_no_duplicates()
    # Buffered readings arrive late but in order: each sensor's rows were stored oldest first.
    stored = harness.stored()
    for sensor in {s for s, _, _ in stored}:
        times = [t for s, t, _ in stored if s == sensor]
        assert times == sorted(times), f"{sensor} stored out of order"
    assert recovery < 20  # paho's reconnect backoff is capped at 10 s
    report("broker outage", outage_s=OUTAGE_SECONDS, buffered=buffered, readings=total,
           all_stored_after_s=round(recovery, 1), lost=0, duplicates=0)


def test_receiver_crash_and_restart_loses_nothing(harness):
    harness.start_receiver()
    harness.start_simulator(count=5, interval=1)
    time.sleep(3)

    harness.kill_receiver()  # SIGKILL: whatever it held in memory is gone
    crashed = time.monotonic()
    time.sleep(OUTAGE_SECONDS)
    sent_while_down = len(harness.sent()) - len(harness.stored())
    harness.start_receiver()
    restarted = time.monotonic()

    harness.wait_until_all_stored(timeout=60)
    recovery = time.monotonic() - restarted
    harness.stop_simulator()
    harness.wait_until_all_stored(timeout=30)
    total = harness.assert_no_loss_no_duplicates()
    assert recovery < 15
    report("receiver crash", down_s=round(restarted - crashed, 1), queued_by_broker=sent_while_down,
           readings=total, backlog_stored_s=round(recovery, 1), lost=0, duplicates=0)


def test_faulty_sensors_bad_messages_rejected_duplicates_stored_once(harness):
    harness.start_receiver()
    harness.start_simulator(count=3, interval=1, FAULT_INVALID_RATE="0.2", FAULT_MALFORMED_RATE="0.2",
                            FAULT_DUPLICATE_RATE="0.3")
    time.sleep(12)
    harness.stop_simulator()
    harness.wait_until_all_stored(timeout=30)
    total = harness.assert_no_loss_no_duplicates()

    simulator, receiver = harness.log("simulator"), harness.log("receiver")
    injected = simulator.count("Fault injected")
    rejected = receiver.count(f"Rejected message on {harness.topic_root}/")
    duplicates = receiver.count("Duplicate telemetry from")
    assert injected and rejected and duplicates, (injected, rejected, duplicates)
    report("fault injection", readings=total, faults_injected=injected, rejected=rejected,
           duplicates_ignored=duplicates, lost=0, duplicates_stored=0)
