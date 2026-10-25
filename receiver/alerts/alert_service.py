"""Threshold alert rules. Pure logic: decides what should change, the repository applies it."""

from dataclasses import dataclass

WARNING = "WARNING"
CRITICAL = "CRITICAL"

OFFLINE = "OFFLINE"  # raised by the offline detector, not by a reading


@dataclass(frozen=True)
class Rule:
    alert_type: str
    field: str
    label: str
    unit: str
    above: bool  # True: alert when the value goes above the thresholds; False: below
    warning: float
    critical: float | None
    # Hysteresis: an active alert resolves only once the value is back past `clear`, so a value
    # hovering around the threshold doesn't raise and resolve an alert on every reading.
    clear: float


# All thresholds lie inside the validator's ranges (sensor-behavior.md), so they are reachable.
RULES = (
    Rule("LOW_BATTERY", "battery", "Battery low", "%", above=False, warning=20, critical=10, clear=25),
    Rule("HIGH_TEMPERATURE", "temperature", "Temperature high", "°C", above=True, warning=50, critical=70, clear=48),
    Rule("LOW_TEMPERATURE", "temperature", "Temperature low", "°C", above=False, warning=0, critical=-20, clear=2),
    Rule("HIGH_HUMIDITY", "humidity", "Humidity high", "%", above=True, warning=90, critical=None, clear=85),
)


@dataclass(frozen=True)
class AlertChange:
    action: str  # RAISE / ESCALATE / RESOLVE
    alert_type: str
    severity: str | None = None
    value: float | None = None
    message: str | None = None


def _past(rule: Rule, value: float, threshold: float) -> bool:
    # Strictly past the threshold: battery 20.0 is fine, 19.99 is low (matches the dashboard).
    return value > threshold if rule.above else value < threshold


def severity_for(rule: Rule, value: float) -> str | None:
    if rule.critical is not None and _past(rule, value, rule.critical):
        return CRITICAL
    if _past(rule, value, rule.warning):
        return WARNING
    return None


def is_cleared(rule: Rule, value: float) -> bool:
    return value <= rule.clear if rule.above else value >= rule.clear


def _message(rule: Rule, severity: str, value: float) -> str:
    threshold = rule.critical if severity == CRITICAL else rule.warning
    direction = "above" if rule.above else "below"
    return f"{rule.label}: {value:g} {rule.unit} ({direction} {threshold:g} {rule.unit})"


class AlertService:
    @staticmethod
    def evaluate(reading: dict, active: dict[str, str]) -> list[AlertChange]:
        """Compare a reading with the sensor's active alerts ({alert_type: severity}).

        At most one active alert per type: a continuing breach doesn't raise a second one, it only
        escalates WARNING -> CRITICAL. Severity never steps back down while the alert is active.
        """
        changes = []
        for rule in RULES:
            value = reading[rule.field]
            severity = severity_for(rule, value)
            current = active.get(rule.alert_type)
            if current is None:
                if severity is not None:
                    changes.append(AlertChange("RAISE", rule.alert_type, severity, value, _message(rule, severity, value)))
            elif current == WARNING and severity == CRITICAL:
                changes.append(AlertChange("ESCALATE", rule.alert_type, severity, value, _message(rule, severity, value)))
            elif is_cleared(rule, value):
                changes.append(AlertChange("RESOLVE", rule.alert_type, value=value))
        return changes
