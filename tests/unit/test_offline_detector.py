import pytest

from storage.offline_detector import format_duration


@pytest.mark.parametrize("seconds, text", [
    (0, "0 s"), (31, "31 s"), (119.9, "119 s"), (120, "2 min"), (7199, "119 min"), (7200, "2 h 0 min"),
    (35842, "9 h 57 min"), (172799, "47 h 59 min"), (172800, "2 days"),
])
def test_offline_duration_is_human_readable(seconds, text):
    assert format_duration(seconds) == text
