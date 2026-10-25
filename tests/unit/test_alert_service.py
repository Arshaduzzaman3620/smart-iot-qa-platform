import pytest

from alerts.alert_service import CRITICAL, RULES, WARNING, AlertService, is_cleared, severity_for
from helpers import valid_telemetry
from validator.telemetry_validator import RANGES

RULE = {rule.alert_type: rule for rule in RULES}


def evaluate(active=None, **reading):
    return AlertService.evaluate(valid_telemetry(**reading), active or {})


def actions(changes):
    return [(c.action, c.alert_type, c.severity) for c in changes]


def test_normal_reading_raises_nothing():
    assert evaluate() == []


@pytest.mark.parametrize(
    "alert_type, value, expected",
    [
        ("LOW_BATTERY", 20.0, None),          # exactly at the threshold is fine (dashboard agrees)
        ("LOW_BATTERY", 19.99, WARNING),
        ("LOW_BATTERY", 10.0, WARNING),
        ("LOW_BATTERY", 9.99, CRITICAL),
        ("LOW_BATTERY", 0, CRITICAL),
        ("HIGH_TEMPERATURE", 50.0, None),
        ("HIGH_TEMPERATURE", 50.01, WARNING),
        ("HIGH_TEMPERATURE", 70.0, WARNING),
        ("HIGH_TEMPERATURE", 70.01, CRITICAL),
        ("HIGH_TEMPERATURE", 85, CRITICAL),
        ("LOW_TEMPERATURE", 0.0, None),
        ("LOW_TEMPERATURE", -0.01, WARNING),
        ("LOW_TEMPERATURE", -20.0, WARNING),
        ("LOW_TEMPERATURE", -20.01, CRITICAL),
        ("LOW_TEMPERATURE", -40, CRITICAL),
        ("HIGH_HUMIDITY", 90.0, None),
        ("HIGH_HUMIDITY", 90.01, WARNING),
        ("HIGH_HUMIDITY", 100, WARNING),       # no critical level for humidity
    ],
)
def test_severity_boundaries(alert_type, value, expected):
    assert severity_for(RULE[alert_type], value) == expected


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.alert_type)
def test_thresholds_are_reachable_within_validator_ranges(rule):
    low, high = RANGES[rule.field]
    for threshold in (rule.warning, rule.critical, rule.clear):
        if threshold is not None:
            assert low < threshold < high


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.alert_type)
def test_clear_level_is_on_the_safe_side_of_the_warning_level(rule):
    # Otherwise an alert would resolve while still breached and be raised again next reading.
    assert severity_for(rule, rule.clear) is None
    assert (rule.clear < rule.warning) if rule.above else (rule.clear > rule.warning)


def test_breach_raises_alert_with_value_and_message():
    [change] = evaluate(battery=15.5)
    assert (change.action, change.alert_type, change.severity, change.value) == ("RAISE", "LOW_BATTERY", WARNING, 15.5)
    assert change.message == "Battery low: 15.5 % (below 20 %)"


def test_critical_message_names_the_critical_threshold():
    [change] = evaluate(temperature=75)
    assert change.message == "Temperature high: 75 °C (above 70 °C)"


def test_several_breaches_in_one_reading_raise_one_alert_each():
    assert actions(evaluate(battery=5, temperature=-30, humidity=95)) == [
        ("RAISE", "LOW_BATTERY", CRITICAL),
        ("RAISE", "LOW_TEMPERATURE", CRITICAL),
        ("RAISE", "HIGH_HUMIDITY", WARNING),
    ]


def test_continuing_breach_does_not_raise_a_duplicate():
    assert evaluate({"LOW_BATTERY": WARNING}, battery=15) == []


def test_warning_escalates_to_critical():
    assert actions(evaluate({"LOW_BATTERY": WARNING}, battery=9)) == [("ESCALATE", "LOW_BATTERY", CRITICAL)]


def test_critical_does_not_step_back_down_while_active():
    assert evaluate({"LOW_BATTERY": CRITICAL}, battery=15) == []


@pytest.mark.parametrize("battery, resolved", [(20.0, False), (24.99, False), (25.0, True), (80, True)])
def test_hysteresis_battery_resolves_only_at_clear_level(battery, resolved):
    expected = [("RESOLVE", "LOW_BATTERY", None)] if resolved else []
    assert actions(evaluate({"LOW_BATTERY": WARNING}, battery=battery)) == expected


@pytest.mark.parametrize("temperature, resolved", [(49, False), (48.01, False), (48.0, True)])
def test_hysteresis_high_temperature(temperature, resolved):
    expected = [("RESOLVE", "HIGH_TEMPERATURE", None)] if resolved else []
    assert actions(evaluate({"HIGH_TEMPERATURE": CRITICAL}, temperature=temperature)) == expected


def test_value_inside_hysteresis_band_without_active_alert_raises_nothing():
    assert evaluate(battery=22) == []


def test_is_cleared_direction():
    assert is_cleared(RULE["LOW_TEMPERATURE"], 2.0)
    assert not is_cleared(RULE["LOW_TEMPERATURE"], 1.99)
    assert is_cleared(RULE["HIGH_HUMIDITY"], 85.0)
    assert not is_cleared(RULE["HIGH_HUMIDITY"], 85.01)


def test_offline_alert_is_ignored_by_threshold_rules():
    # OFFLINE is resolved by the repository on any message, not by the threshold rules.
    assert evaluate({"OFFLINE": WARNING}) == []

