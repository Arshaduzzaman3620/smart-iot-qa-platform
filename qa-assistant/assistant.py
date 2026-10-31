"""Calls Claude for the two QA tasks. No CLI or file handling here; the client is passed in, so tests
use a fake one and never call the API."""

import anthropic

from context import existing_tests, failing_part, project_docs
from schemas import FailureAnalysis, TestPlan

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16_000  # non-streaming: enough for a full plan, within the SDK's request timeout
# Refusal fallback (server side): if a safety classifier declines, the API re-runs the request on the
# recommended model for that refusal category instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

ROLE = """You are the QA engineer on the SmartIoT Sensor Quality Engineering Platform, a fictional,
fully simulated IoT system: sensor simulator -> MQTT (Mosquitto) -> receiver (parse, validate, store)
-> MySQL -> FastAPI (JWT roles VIEWER/OPERATOR/ADMIN) -> React dashboard. The project documentation is
below; treat it as the specification. Ground every test case and every diagnosis in it: use the real
value ranges, endpoints, status codes, roles, topics and test layers it defines. Where the input leaves
something open, state the assumption instead of inventing behaviour."""


class AssistantError(Exception):
    """The request could not produce a usable answer (refusal, cut-off output, API error)."""


def _system() -> list[dict]:
    return [{"type": "text", "text": f"{ROLE}\n\n<project_docs>\n{project_docs()}\n</project_docs>\n\n"
                                     f"<existing_tests>\n{existing_tests()}\n</existing_tests>"}]


def _ask(client, prompt: str, schema):
    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "high"},  # careful analysis is the point; this model defaults to medium
            cache_control={"type": "ephemeral"},  # the docs prefix repeats on every call
            system=_system(),
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
    except anthropic.AuthenticationError:
        raise AssistantError("The Anthropic API rejected the credentials (check ANTHROPIC_API_KEY)") from None
    except anthropic.RateLimitError as exc:
        retry = exc.response.headers.get("retry-after", "a while")
        raise AssistantError(f"Rate limited by the Anthropic API; retry after {retry} s") from None
    except anthropic.APIStatusError as exc:
        raise AssistantError(f"Anthropic API error {exc.status_code}: {exc.message}") from None
    except anthropic.APIConnectionError:
        raise AssistantError("Could not reach the Anthropic API (network?)") from None

    if response.stop_reason == "refusal":
        details = response.stop_details
        reason = f" ({details.category}: {details.explanation})" if details else ""
        raise AssistantError(f"The model declined this request{reason}")
    if response.stop_reason == "max_tokens":
        raise AssistantError("The answer was cut off at the token limit; narrow the input and try again")
    if response.parsed_output is None:
        raise AssistantError("The model returned no structured answer")
    return response.parsed_output


def generate_test_cases(client, requirement: str) -> TestPlan:
    prompt = f"""Design test cases for this requirement or change:

<requirement>
{requirement}
</requirement>

Cover positive, negative and boundary cases (use the exact boundaries from the docs, e.g. +/-0.01 around
a range limit). Put each case in the test layer where it is cheapest to check reliably, per the testing
strategy. If <existing_tests> already covers a case, name that test in already_covered_by. List what you
had to assume, and any risks the cases leave open, in assumptions and gaps."""
    return _ask(client, prompt, TestPlan)


def analyze_failures(client, pytest_log: str) -> tuple[FailureAnalysis, bool]:
    """Returns the analysis and whether the log had to be shortened (oldest part dropped)."""
    log, truncated = failing_part(pytest_log)
    note = "\n(The start of the log was dropped for length; the failures section is complete.)" if truncated else ""
    prompt = f"""Analyse this failing pytest run of the project.{note}

<pytest_log>
{log}
</pytest_log>

For each failing test: classify it (a product defect, a test defect, the environment such as a service
not running, flakiness such as timing, or unknown), give the most likely cause, quote the log lines it
rests on as evidence, and the next concrete step. If several failures share one cause, say so in
shared_root_cause. Only claim what the log and docs support; say "unknown" otherwise."""
    return _ask(client, prompt, FailureAnalysis), truncated
