# AI QA Assistant

A command-line helper in [qa-assistant/](../../qa-assistant/) that uses Claude (Anthropic API) for two QA chores (Phase 16):

1. **`generate-tests`**: turns a requirement, user story or design doc into test cases (positive, negative, boundary), each placed in the right test layer. It marks the ones this repository already covers and lists its assumptions and open questions.
2. **`analyze-failures`**: reads a failing pytest run and, for each failure, gives a category (product defect, test defect, environment, flaky, unknown), the likely cause with the log lines it rests on, and the next step. It says when several failures share one root cause.

The project's own docs (requirements, sensor ranges, topics, API, auth, alerts, commands, FOTA, testing strategy) and the names of all existing tests go into the prompt as the **specification**, so answers use this platform's real limits, status codes and roles, not generic IoT guesses.

## Use

It needs an Anthropic API key (`ANTHROPIC_API_KEY`). The test image already has everything else installed:

```bash
export ANTHROPIC_API_KEY=sk-ant-...

docker compose -f compose.test.yaml run --rm tests \
  python qa-assistant/main.py generate-tests --text "Operators can change a sensor's reporting interval (1-3600 s)"

docker compose -f compose.test.yaml run --rm tests \
  python qa-assistant/main.py generate-tests --file docs/architecture/fota.md --out fota-test-plan.md

# Analyse a failing run (save pytest's output first)
docker compose -f compose.test.yaml run --rm tests sh -c "pytest tests/mqtt > run.log; python qa-assistant/main.py analyze-failures --log run.log"
```

Add `--json` for machine-readable output (for example, to feed a test management tool). On the host with Python 3.12: `pip install -r qa-assistant/requirements.txt`, then the same commands without the Docker prefix.

## How it works

| Choice | Why |
|---|---|
| Model `claude-opus-5-5`, `effort: high` | Test design and diagnosis are reasoning-heavy. This model's default effort is `medium`, so it is set explicitly. |
| **Structured outputs** (`client.beta.messages.parse` with Pydantic models in [schemas.py](../../qa-assistant/schemas.py)) | The answer is guaranteed to be valid JSON in exactly the `TestPlan` / `FailureAnalysis` shape. Nothing parses free text, and Markdown is rendered from the validated objects. |
| **Prompt caching** (`cache_control`) | The docs prefix is identical on every call, so repeated calls read it from cache instead of paying for it again |
| **Refusal fallback** (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) | If a safety classifier declines a request (unlikely for QA text, but possible with security-test wording), the API retries on the recommended model server-side |
| Every non-answer is an error | `refusal` (with its category), `max_tokens` (cut off), no parsed output, and each API error class (auth, 429 with `Retry-After`, 5xx, network) become one clear message and exit code 1, never a traceback or a half plan |
| Logs: the failures section, never silently cut | It starts at pytest's `FAILURES` / `ERRORS` section. Above about 300 000 characters the oldest part is dropped, and the output **says so**. A log with no failures isn't sent at all. |
| No API call in tests | [tests/unit/test_qa_assistant.py](../../tests/unit/test_qa_assistant.py) uses a fake client. 17 tests cover the exact request (model, schema, fallback, effort, cache, docs as context), refusal, cut-off, missing output, every API error class, log selection, rendering, and the CLI paths. CI never needs a key. |

## Limits

- **It suggests; people decide.** Generated cases are a review starting point: check them against the spec before automating. A failure analysis is a hypothesis with evidence attached, not a verdict.
- **Costs money per call** (Opus 5.5: $4 / $20 per million input / output tokens; the docs and test-name context is about 60 000 characters, roughly 15k–20k tokens, cached after the first call). Nothing calls it automatically.
- **Text only:** it reads what you give it and the docs, not the database or live services.
- Not run against the live API while building this phase (no key on the build machine). The request shape is pinned by the tests against SDK 2.3.0. Running one of the commands above with your key is the remaining manual check.
