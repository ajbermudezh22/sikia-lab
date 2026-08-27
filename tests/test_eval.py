from __future__ import annotations

from sikia_lab.eval.harness import Case, _parse_scores, run_eval
from sikia_lab.eval.rubric import CLINICAL_NOTE
from sikia_lab.providers.fake import FakeLLM
from sikia_lab.router import Router


def test_rubric_weights_safety_criteria_above_style():
    strong_safety = {"faithfulness": 1.0, "completeness": 1.0, "structure": 0.0, "uncertainty": 1.0}
    strong_style = {"faithfulness": 0.0, "completeness": 0.0, "structure": 1.0, "uncertainty": 0.0}

    safety_score, _ = CLINICAL_NOTE.score(strong_safety)
    style_score, _ = CLINICAL_NOTE.score(strong_style)

    assert safety_score > style_score


def test_floor_breach_is_reported_even_when_the_average_looks_fine():
    scores = {
        "faithfulness": 0.4,  # below its 0.8 floor: a hallucination
        "completeness": 1.0,
        "structure": 1.0,
        "uncertainty": 1.0,
    }

    weighted, breached = CLINICAL_NOTE.score(scores)

    assert weighted > 0.6, "a flat average would call this a decent note"
    assert breached == ["faithfulness"]


def test_missing_criterion_is_an_error_not_a_zero():
    try:
        CLINICAL_NOTE.score({"faithfulness": 1.0})
    except ValueError as exc:
        assert "completeness" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_unparseable_judge_response_scores_zero_rather_than_passing():
    scores = _parse_scores("the model rambled and never emitted json", CLINICAL_NOTE)

    assert set(scores) == {c.name for c in CLINICAL_NOTE.criteria}
    assert all(v == 0.0 for v in scores.values())


def test_judge_json_is_extracted_from_surrounding_prose():
    raw = (
        'Sure! Here you go:\n{"scores": {"faithfulness": 0.9, "completeness": 0.8, '
        '"structure": 1.0, "uncertainty": 0.7}}\nHope that helps.'
    )

    scores = _parse_scores(raw, CLINICAL_NOTE)

    assert scores["faithfulness"] == 0.9


async def test_run_eval_flags_cases_missing_required_content():
    cases = [
        Case(id="mentions-drug", transcript="patient on metformin", must_mention=("metformin",)),
    ]
    judge = Router([FakeLLM("judge", priority=0)])

    async def generate(transcript: str) -> str:
        return "Subjective: patient reports feeling unwell."  # drops the drug name

    report = await run_eval(cases, generate, judge, CLINICAL_NOTE)

    assert report.results[0].missing_mentions == ["metformin"]
    assert not report.results[0].passed
    assert report.pass_rate == 0.0
