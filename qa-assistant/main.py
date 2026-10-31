"""AI QA assistant (Phase 16). Uses the Claude API with this project's docs as the specification.

  python qa-assistant/main.py generate-tests --text "Operators can rename a sensor (max 100 chars)"
  python qa-assistant/main.py generate-tests --file docs/architecture/fota.md --out plan.md
  pytest > run.log; python qa-assistant/main.py analyze-failures --log run.log

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile). Add --json for machine-readable output.
"""

import argparse
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required (3.12 recommended). Or run it in Docker: docs/testing/ai-qa-assistant.md")

import anthropic

from assistant import AssistantError, analyze_failures, generate_test_cases
from report import analysis_markdown, plan_markdown


def read_input(text: str | None, file: str | None) -> str:
    if text:
        return text
    if file == "-":
        return sys.stdin.read()
    return Path(file).read_text(encoding="utf-8")


def make_client():
    try:
        return anthropic.Anthropic()
    except anthropic.AnthropicError as exc:
        raise AssistantError(f"No Anthropic credentials: set ANTHROPIC_API_KEY ({exc})") from None


def main(argv=None, client_factory=make_client) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate-tests", help="design test cases for a requirement or doc")
    source = gen.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="the requirement itself")
    source.add_argument("--file", help="a file with the requirement, or - for stdin")
    analyze = commands.add_parser("analyze-failures", help="explain a failing pytest run")
    analyze.add_argument("--log", required=True, help="pytest output saved to a file, or - for stdin")
    for command in (gen, analyze):
        command.add_argument("--out", help="write the result here instead of stdout")
        command.add_argument("--json", action="store_true", help="JSON instead of Markdown")
    args = parser.parse_args(argv)

    try:
        if args.command == "generate-tests":
            requirement = read_input(args.text, args.file).strip()
            if not requirement:
                raise AssistantError("The requirement is empty")
            plan = generate_test_cases(client_factory(), requirement)
            output = plan.model_dump_json(indent=2) if args.json else plan_markdown(plan)
        else:
            log = read_input(None, args.log)
            if "FAILED" not in log and "ERROR" not in log:
                raise AssistantError("No failures in this log (no FAILED or ERROR lines): nothing to analyse")
            analysis, truncated = analyze_failures(client_factory(), log)
            if truncated:
                print("Note: the log was long; its start was dropped, the failures were kept.", file=sys.stderr)
            output = analysis.model_dump_json(indent=2) if args.json else analysis_markdown(analysis, truncated)
    except (AssistantError, OSError) as exc:
        print(f"qa-assistant: {exc}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
