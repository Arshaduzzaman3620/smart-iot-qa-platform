"""The AI QA assistant (qa-assistant/, Phase 16) with a fake Claude client: what it sends, and how it
handles every kind of answer. No test calls the real API."""

import importlib.util
import json
import sys
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from helpers import ROOT

sys.path.insert(0, str(ROOT / "qa-assistant"))
import assistant  # noqa: E402
from context import existing_tests, failing_part, project_docs  # noqa: E402
from report import analysis_markdown, plan_markdown  # noqa: E402
from schemas import FailureAnalysis, FailureFinding, TestCase, TestPlan  # noqa: E402

_spec = importlib.util.spec_from_file_location("qa_main", ROOT / "qa-assistant" / "main.py")
qa_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa_main)

PLAN = TestPlan(feature="Rename a sensor", assumptions=["names are trimmed"], gaps=["unicode width"], cases=[
    TestCase(id="TC-1", title="Name of 100 chars accepted", layer="api", kind="boundary", priority="high",
             preconditions=["OPERATOR token"], steps=["PATCH name of 100 chars"], expected="200",
             already_covered_by="tests/api/test_users.py::test_name_of_exactly_100_chars_is_accepted"),
    TestCase(id="TC-2", title="Viewer cannot rename", layer="api", kind="negative", priority="high",
             preconditions=[], steps=["PATCH as VIEWER"], expected="403", already_covered_by=None),
])
ANALYSIS = FailureAnalysis(summary="Broker not running", shared_root_cause="MQTT broker down",
                           next_steps=["docker compose up -d mqtt"], findings=[
    FailureFinding(test="tests/mqtt/test_broker.py::test_round_trip", category="environment",
                   likely_cause="no broker", evidence="ConnectionRefusedError", next_step="start mqtt")])

FAILING_LOG = """============ test session starts ============
tests/unit/test_x.py ....
================== FAILURES ==================
___ test_round_trip ___
E   ConnectionRefusedError: [Errno 111] Connection refused
FAILED tests/mqtt/test_broker.py::test_round_trip - ConnectionRefusedError
"""


class FakeClient:
    def __init__(self, parsed=None, stop_reason="end_turn", stop_details=None, error=None):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._result = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, stop_details=stop_details)
        self._error = error

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._result


def api_error(cls, status, headers=None):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, headers=headers or {}, request=request, json={"error": {"message": "x"}})
    return cls("x", response=response, body=None)


# ---- the request ---------------------------------------------------------------------------------

def test_generate_sends_the_requirement_with_project_docs_as_the_spec():
    client = FakeClient(parsed=PLAN)
    assert assistant.generate_test_cases(client, "Operators can rename a sensor") == PLAN
    (call,) = client.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is TestPlan
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {"effort": "high"}
    assert call["cache_control"] == {"type": "ephemeral"}
    system = call["system"][0]["text"]
    assert "| Temperature | -40 °C | 85 °C |" in system          # real ranges from sensor-behavior.md
    assert "test_name_of_exactly_100_chars_is_accepted" in system  # what is already covered
    assert "Operators can rename a sensor" in call["messages"][0]["content"]
    assert "thinking" not in call and "temperature" not in call  # neither is accepted by this model


def test_analyze_sends_the_failures_section():
    client = FakeClient(parsed=ANALYSIS)
    analysis, truncated = assistant.analyze_failures(client, FAILING_LOG)
    assert analysis == ANALYSIS and truncated is False
    prompt = client.calls[0]["messages"][0]["content"]
    assert "ConnectionRefusedError" in prompt
    assert "test session starts" not in prompt  # passing preamble left out
    assert client.calls[0]["output_format"] is FailureAnalysis


# ---- answers that are not usable -----------------------------------------------------------------

def test_refusal_is_reported_with_its_reason():
    details = SimpleNamespace(category="cyber", explanation="declined")
    with pytest.raises(assistant.AssistantError, match=r"declined this request \(cyber: declined\)"):
        assistant.generate_test_cases(FakeClient(stop_reason="refusal", stop_details=details), "x")


def test_cut_off_answer_is_an_error_not_a_partial_plan():
    with pytest.raises(assistant.AssistantError, match="cut off"):
        assistant.generate_test_cases(FakeClient(parsed=PLAN, stop_reason="max_tokens"), "x")


def test_missing_structured_output_is_an_error():
    with pytest.raises(assistant.AssistantError, match="no structured answer"):
        assistant.generate_test_cases(FakeClient(parsed=None), "x")


@pytest.mark.parametrize("error, message", [
    (lambda: api_error(anthropic.AuthenticationError, 401), "credentials"),
    (lambda: api_error(anthropic.RateLimitError, 429, {"retry-after": "30"}), "retry after 30 s"),
    (lambda: api_error(anthropic.InternalServerError, 500), "API error 500"),
    (lambda: anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")), "Could not reach"),
])
def test_api_errors_become_clear_messages(error, message):
    with pytest.raises(assistant.AssistantError, match=message):
        assistant.generate_test_cases(FakeClient(error=error()), "x")


# ---- context ---------------------------------------------------------------------------------------

def test_project_docs_and_existing_tests_are_read_from_the_repo():
    docs = project_docs()
    assert '<doc path="docs/api/auth.md">' in docs and "VIEWER" in docs
    assert "tests/unit/test_qa_assistant.py: test_generate_sends" in existing_tests()


def test_long_log_keeps_the_end_and_says_so():
    log = "x" * 1000 + "\n= FAILURES =\n" + "y" * 50
    kept, truncated = failing_part(log, limit=10_000)
    assert kept.startswith("= FAILURES =") and not truncated
    kept, truncated = failing_part("z" * 500, limit=100)
    assert kept == "z" * 100 and truncated


# ---- rendering and CLI -----------------------------------------------------------------------------

def test_plan_markdown_lists_every_case_and_coverage():
    md = plan_markdown(PLAN)
    assert "# Test cases: Rename a sensor" in md
    assert "| TC-2 | Viewer cannot rename | api | negative | high | new |" in md
    assert "test_users.py::test_name_of_exactly_100_chars_is_accepted" in md
    assert "**Expected:** 403" in md and "- unicode width" in md


def test_analysis_markdown_notes_truncation():
    md = analysis_markdown(ANALYSIS, truncated=True)
    assert "**Shared root cause:** MQTT broker down" in md and "start was dropped" in md
    assert "- **Category:** environment" in md


def test_cli_generate_markdown_and_json(capsys, tmp_path):
    assert qa_main.main(["generate-tests", "--text", "rename"], client_factory=lambda: FakeClient(parsed=PLAN)) == 0
    assert "# Test cases: Rename a sensor" in capsys.readouterr().out
    out = tmp_path / "plan.json"
    assert qa_main.main(["generate-tests", "--text", "rename", "--json", "--out", str(out)],
                        client_factory=lambda: FakeClient(parsed=PLAN)) == 0
    assert json.loads(out.read_text())["cases"][1]["id"] == "TC-2"


def test_cli_refuses_a_log_without_failures(capsys, tmp_path):
    log = tmp_path / "ok.log"
    log.write_text("120 passed in 3.2s\n")
    calls = []
    assert qa_main.main(["analyze-failures", "--log", str(log)], client_factory=lambda: calls.append(1)) == 1
    assert "nothing to analyse" in capsys.readouterr().err
    assert calls == []  # no API call made


def test_cli_reports_missing_credentials_without_a_traceback(capsys):
    def no_credentials():
        raise assistant.AssistantError("No Anthropic credentials: set ANTHROPIC_API_KEY")

    assert qa_main.main(["generate-tests", "--text", "x"], client_factory=no_credentials) == 1
    assert "qa-assistant: No Anthropic credentials" in capsys.readouterr().err


def test_cli_rejects_an_empty_requirement(capsys):
    assert qa_main.main(["generate-tests", "--text", "   "], client_factory=lambda: FakeClient(parsed=PLAN)) == 1
    assert "empty" in capsys.readouterr().err
