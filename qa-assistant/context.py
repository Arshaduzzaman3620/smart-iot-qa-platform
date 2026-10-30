"""Project knowledge given to the model, read from the repository's own docs, so its answers use this
platform's real ranges, endpoints, roles and test layout -- not generic IoT guesses."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The docs that define behaviour and the test approach. Stable between runs, so they are prompt-cached.
DOCS = [
    "docs/requirements/requirements.md",
    "docs/architecture/sensor-behavior.md",
    "docs/mqtt/topics.md",
    "docs/api/endpoints.md",
    "docs/api/auth.md",
    "docs/architecture/alerts.md",
    "docs/architecture/commands.md",
    "docs/architecture/fota.md",
    "docs/testing/strategy.md",
    "docs/testing/automation.md",
]

MAX_LOG_CHARS = 300_000  # ~75k tokens; beyond that the start (passing tests) is dropped, and the CLI says so


def project_docs(root: Path = ROOT) -> str:
    parts = []
    for rel in DOCS:
        path = root / rel
        if path.exists():
            parts.append(f'<doc path="{rel}">\n{path.read_text(encoding="utf-8")}\n</doc>')
    return "\n\n".join(parts)


def existing_tests(root: Path = ROOT) -> str:
    """Test names per file, so the assistant can say what is already covered."""
    lines = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        names = re.findall(r"^def (test_\w+)", path.read_text(encoding="utf-8"), flags=re.M)
        if names:
            lines.append(f"{path.relative_to(root)}: {', '.join(names)}")
    return "\n".join(lines)


def failing_part(log: str, limit: int = MAX_LOG_CHARS) -> tuple[str, bool]:
    """The part of a pytest log worth reading: from the first FAILURES/ERRORS section on. Never cut
    silently -- the second value says whether the start was dropped."""
    for marker in ("= FAILURES =", "= ERRORS ="):
        index = log.find(marker)
        if index != -1:
            log = log[log.rfind("\n", 0, index) + 1:]
            break
    if len(log) <= limit:
        return log, False
    return log[-limit:], True
