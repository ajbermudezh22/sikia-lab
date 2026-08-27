"""Offline LLM-as-judge evaluation.

Runs a set of cases through the system under test, asks a judge model to score each
output against a rubric, and aggregates. Two decisions worth naming:

* The judge is a separate router from the production one. Judging with the model
  you are grading is how you get a system that rates itself well.
* Results carry the per-case detail, not just the mean. An eval that only reports an
  average tells you something changed but never what — and the failing cases are the
  entire point.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import structlog

from sikia_lab.eval.rubric import Rubric
from sikia_lab.router import Router

log = structlog.get_logger(__name__)

JUDGE_PROMPT = """\
You are grading a generated clinical note against the source transcript.
Score each criterion from 0.0 to 1.0. Respond with JSON only: {{"scores": {{...}}}}

Criteria:
{criteria}

Transcript:
{transcript}

Generated note:
{output}
"""


@dataclass
class Case:
    id: str
    transcript: str
    # What a correct note must contain; used for cheap deterministic checks alongside
    # the judge, so a broken judge cannot silently pass everything.
    must_mention: tuple[str, ...] = ()


@dataclass
class CaseResult:
    case_id: str
    output: str
    scores: dict[str, float]
    weighted: float
    breached: list[str] = field(default_factory=list)
    missing_mentions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.breached and not self.missing_mentions


@dataclass
class EvalReport:
    rubric: str
    results: list[CaseResult]

    @property
    def mean_score(self) -> float:
        return sum(r.weighted for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    def summary(self) -> str:
        lines = [
            f"rubric: {self.rubric}",
            f"cases: {len(self.results)}",
            f"mean weighted score: {self.mean_score:.3f}",
            f"pass rate: {self.pass_rate:.0%}",
            "",
        ]
        for r in sorted(self.results, key=lambda r: r.weighted):
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.case_id}  score={r.weighted:.3f}")
            if r.breached:
                lines.append(f"         floor breached: {', '.join(r.breached)}")
            if r.missing_mentions:
                lines.append(f"         never mentioned: {', '.join(r.missing_mentions)}")
        return "\n".join(lines)


def _parse_scores(raw: str, rubric: Rubric) -> dict[str, float]:
    """Pull scores out of a judge response, tolerating prose around the JSON."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
            scores = payload.get("scores", payload)
            if isinstance(scores, dict):
                parsed = {
                    c.name: float(scores[c.name]) for c in rubric.criteria if c.name in scores
                }
                if len(parsed) == len(rubric.criteria):
                    return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # An unparseable judge response is a failed judgement, not a passing case.
    log.warning("judge.unparseable", raw=raw[:200])
    return {c.name: 0.0 for c in rubric.criteria}


async def run_eval(
    cases: list[Case],
    generate: Callable[[str], Awaitable[str]],
    judge_router: Router,
    rubric: Rubric,
    *,
    concurrency: int = 4,
) -> EvalReport:
    semaphore = asyncio.Semaphore(concurrency)
    criteria_text = "\n".join(f"- {c.name}: {c.question}" for c in rubric.criteria)

    async def run_case(case: Case) -> CaseResult:
        async with semaphore:
            output = await generate(case.transcript)
            prompt = JUDGE_PROMPT.format(
                criteria=criteria_text, transcript=case.transcript, output=output
            )
            verdict = await judge_router.call(lambda p: p.complete(prompt))

        scores = _parse_scores(verdict.text, rubric)
        weighted, breached = rubric.score(scores)
        missing = [m for m in case.must_mention if m.lower() not in output.lower()]
        return CaseResult(
            case_id=case.id,
            output=output,
            scores=scores,
            weighted=weighted,
            breached=breached,
            missing_mentions=missing,
        )

    results = await asyncio.gather(*(run_case(c) for c in cases))
    return EvalReport(rubric=rubric.name, results=list(results))
