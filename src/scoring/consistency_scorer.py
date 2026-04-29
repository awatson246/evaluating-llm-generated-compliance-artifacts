"""
Cross-run consistency scorer.

NOT YET IMPLEMENTED — implement SchemaScorer first, then come back here.

Intended interface:

    scorer = ConsistencyScorer()
    result = scorer.score(runs)

    runs    list of ScoringResult.to_dict() outputs for the *same* (model, task, level) condition
    result.field_stability      dict[field_id, float]   1.0 = always same, 0.0 = maximally unstable
    result.overall_consistency  float                   mean field stability across all fields
    result.stable_fields        list[str]               IDs where stability >= threshold
    result.unstable_fields      list[str]               IDs where stability < threshold
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsistencyResult:
    field_stability: dict[str, float] = field(default_factory=dict)
    overall_consistency: float = 0.0
    stable_fields: list[str] = field(default_factory=list)
    unstable_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field_stability": self.field_stability,
            "overall_consistency": self.overall_consistency,
            "stable_fields": self.stable_fields,
            "unstable_fields": self.unstable_fields,
        }


class ConsistencyScorer:
    def __init__(self, stability_threshold: float = 1.0):
        """
        Args:
            stability_threshold: fields with stability >= this value are labelled 'stable'
        """
        self.stability_threshold = stability_threshold

    def score(self, runs: list[dict]) -> ConsistencyResult:
        """
        Compute field-level consistency across multiple runs of the same condition.

        Args:
            runs: list of ScoringResult.to_dict() outputs for the same (model, task, level)

        Returns:
            ConsistencyResult with per-field stability and overall consistency score
        """
        raise NotImplementedError(
            "ConsistencyScorer.score() is not yet implemented. "
            "Implement SchemaScorer first."
        )
