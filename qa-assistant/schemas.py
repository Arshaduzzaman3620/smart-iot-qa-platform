"""What the assistant returns, as Pydantic models: the API's structured outputs guarantee valid JSON in
exactly this shape, so nothing downstream parses free text."""

from typing import Literal

from pydantic import BaseModel

Layer = Literal["unit", "api", "mqtt", "integration", "ui", "e2e", "reliability", "security", "performance"]


class TestCase(BaseModel):
    __test__ = False  # a data model, not a pytest test class
    id: str                      # e.g. TC-AUTH-01
    title: str
    layer: Layer                 # where in tests/ it belongs
    kind: Literal["positive", "negative", "boundary"]
    priority: Literal["high", "medium", "low"]
    preconditions: list[str]
    steps: list[str]
    expected: str
    already_covered_by: str | None  # an existing test, if the project already has one


class TestPlan(BaseModel):
    __test__ = False
    feature: str
    assumptions: list[str]       # what the assistant had to assume because the input didn't say
    cases: list[TestCase]
    gaps: list[str]              # risks the cases don't cover, or questions for the author


class FailureFinding(BaseModel):
    test: str                    # pytest node id
    category: Literal["product_defect", "test_defect", "environment", "flaky", "unknown"]
    likely_cause: str
    evidence: str                # the log lines it is based on, quoted
    next_step: str


class FailureAnalysis(BaseModel):
    summary: str
    findings: list[FailureFinding]
    shared_root_cause: str | None  # when several failures come from one cause
    next_steps: list[str]
