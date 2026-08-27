"""Rubrics for judging generated clinical notes.

Criteria are weighted because they are not equally dangerous. A hallucinated finding
in a medical note is a different class of problem from an awkward sentence, and a
flat average would let good prose hide a safety failure — so `Rubric.score` also
reports whether any critical criterion fell below its floor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Criterion:
    name: str
    question: str
    weight: float
    # A score below this on a critical criterion fails the case outright.
    floor: float | None = None


@dataclass(frozen=True)
class Rubric:
    name: str
    criteria: tuple[Criterion, ...]

    def score(self, per_criterion: dict[str, float]) -> tuple[float, list[str]]:
        """Return (weighted score in 0..1, list of criteria that breached their floor)."""
        missing = {c.name for c in self.criteria} - per_criterion.keys()
        if missing:
            raise ValueError(f"missing scores for: {sorted(missing)}")

        total_weight = sum(c.weight for c in self.criteria)
        weighted = sum(per_criterion[c.name] * c.weight for c in self.criteria) / total_weight

        breached = [
            c.name for c in self.criteria if c.floor is not None and per_criterion[c.name] < c.floor
        ]
        return weighted, breached


CLINICAL_NOTE = Rubric(
    name="clinical_note_v1",
    criteria=(
        Criterion(
            name="faithfulness",
            question=(
                "Does every clinical claim in the note appear in the transcript? "
                "Score 0 if anything is invented. This is the safety criterion."
            ),
            weight=3.0,
            floor=0.8,
        ),
        Criterion(
            name="completeness",
            question="Are the clinically significant facts from the transcript present?",
            weight=2.0,
            floor=0.5,
        ),
        Criterion(
            name="structure",
            question="Does the note follow Subjective / Objective / Assessment / Plan?",
            weight=1.0,
        ),
        Criterion(
            name="uncertainty",
            question="Is unclear audio marked as [unclear] rather than guessed at?",
            weight=1.5,
            floor=0.5,
        ),
    ),
)
