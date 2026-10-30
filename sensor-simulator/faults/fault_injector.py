"""Deliberately bad messages, for testing how the rest of the system copes (Phase 15f).
No MQTT here: given a reading, return the payload(s) to publish instead."""

import json
import random
from dataclasses import dataclass


@dataclass
class FaultRates:
    """Probability (0-1) per reading of each fault. All zero = a well-behaved sensor."""

    invalid: float = 0.0     # a value out of range (the receiver must reject it)
    malformed: float = 0.0   # truncated JSON (the receiver must reject it)
    duplicate: float = 0.0   # the same message twice (the receiver must store it once)

    def __post_init__(self):
        for name in ("invalid", "malformed", "duplicate"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"fault rate {name} must be between 0 and 1, got {value}")

    @property
    def any(self) -> bool:
        return bool(self.invalid or self.malformed or self.duplicate)


def apply_faults(reading: dict, rates: FaultRates, rng: random.Random) -> tuple[list[bytes], list[str]]:
    """The payloads to publish for `reading`, and the names of the faults applied (for the log)."""
    if not rates.any:
        return [json.dumps(reading).encode()], []
    faults = []
    if rng.random() < rates.invalid:
        reading = {**reading, "temperature": 999.0}
        faults.append("invalid")
    payload = json.dumps(reading).encode()
    if rng.random() < rates.malformed:
        payload = payload[: len(payload) // 2]
        faults.append("malformed")
    payloads = [payload]
    if rng.random() < rates.duplicate:
        payloads.append(payload)
        faults.append("duplicate")
    return payloads, faults
