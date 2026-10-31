"""Markdown for people: a test plan to review, a failure analysis to act on."""

from schemas import FailureAnalysis, TestPlan


def _bullets(items: list[str], empty: str = "none") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def plan_markdown(plan: TestPlan) -> str:
    lines = [f"# Test cases: {plan.feature}", "", "## Assumptions", _bullets(plan.assumptions), "",
             "## Cases", "", "| ID | Title | Layer | Kind | Priority | Already covered by |", "|---|---|---|---|---|---|"]
    for case in plan.cases:
        lines.append(f"| {case.id} | {case.title} | {case.layer} | {case.kind} | {case.priority} | "
                     f"{case.already_covered_by or 'new'} |")
    for case in plan.cases:
        lines += ["", f"### {case.id}: {case.title}", "", "**Preconditions**", _bullets(case.preconditions), "",
                  "**Steps**", *(f"{i}. {step}" for i, step in enumerate(case.steps, 1)), "",
                  f"**Expected:** {case.expected}"]
    lines += ["", "## Gaps and open questions", _bullets(plan.gaps)]
    return "\n".join(lines) + "\n"


def analysis_markdown(analysis: FailureAnalysis, truncated: bool = False) -> str:
    lines = ["# Failure analysis", "", analysis.summary, ""]
    if truncated:
        lines += ["> The log was long: its start was dropped, the failures section was analysed in full.", ""]
    if analysis.shared_root_cause:
        lines += [f"**Shared root cause:** {analysis.shared_root_cause}", ""]
    for finding in analysis.findings:
        lines += [f"## {finding.test}", "", f"- **Category:** {finding.category.replace('_', ' ')}",
                  f"- **Likely cause:** {finding.likely_cause}", f"- **Evidence:** {finding.evidence}",
                  f"- **Next step:** {finding.next_step}", ""]
    lines += ["## Next steps", _bullets(analysis.next_steps)]
    return "\n".join(lines) + "\n"
