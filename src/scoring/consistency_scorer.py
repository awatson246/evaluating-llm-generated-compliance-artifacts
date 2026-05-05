"""
Cross-run consistency scorer.

Takes the per-run ScoringResults for a single (model, task, vagueness_level) condition
and computes how stable each field's presence is across runs.

  field_stability[field_id] = fraction of runs in which the field was detected (0–1).
    1.0 = present in every run  |  0.0 = absent in every run
    Values between 0 and 1 indicate inconsistent inclusion.

  overall_consistency = mean field_stability across all fields evaluated.

  stable_fields   = field IDs with stability >= stability_threshold
  unstable_fields = field IDs with stability <  stability_threshold

Default threshold is 1.0 (a field must appear in *every* run to be called stable),
which directly captures the reproducibility requirement described in the paper.
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
            "field_stability":    self.field_stability,
            "overall_consistency": self.overall_consistency,
            "stable_fields":      self.stable_fields,
            "unstable_fields":    self.unstable_fields,
        }


class ConsistencyScorer:
    def __init__(self, stability_threshold: float = 1.0):
        """
        Args:
            stability_threshold: fields with stability >= this value are labelled
                                 'stable'. 1.0 means the field must appear in every
                                 run; 0.667 means at least 2 out of 3 runs.
        """
        self.stability_threshold = stability_threshold

    def score(self, scoring_results: list[dict]) -> ConsistencyResult:
        """
        Compute field-level consistency across multiple runs of the same condition.

        Args:
            scoring_results: list of ScoringResult.to_dict() outputs, all from the
                             same (model, task, vagueness_level) group.

        Returns:
            ConsistencyResult with per-field stability and overall consistency.
        """
        if not scoring_results:
            raise ValueError("scoring_results must not be empty")

        n = len(scoring_results)

        # Collect every field_id seen across all runs
        all_field_ids: set[str] = set()
        for r in scoring_results:
            all_field_ids.update(r.get("field_scores", {}).keys())

        # Stability = fraction of runs in which the field was detected (True)
        field_stability: dict[str, float] = {
            fid: sum(
                bool(r.get("field_scores", {}).get(fid, False))
                for r in scoring_results
            ) / n
            for fid in sorted(all_field_ids)
        }

        stable   = [fid for fid, s in field_stability.items() if s >= self.stability_threshold]
        unstable = [fid for fid, s in field_stability.items() if s <  self.stability_threshold]

        overall = sum(field_stability.values()) / len(field_stability) if field_stability else 0.0

        return ConsistencyResult(
            field_stability={fid: round(s, 4) for fid, s in field_stability.items()},
            overall_consistency=round(overall, 4),
            stable_fields=sorted(stable),
            unstable_fields=sorted(unstable),
        )
