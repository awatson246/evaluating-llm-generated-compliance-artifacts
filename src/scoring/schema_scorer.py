"""
Schema-based field completeness scorer.

NOT YET IMPLEMENTED — finalize schemas
Collect raw outputs first via run_experiment.py, then come back to this module.

Intended interface (do not change signatures without also updating run_experiment.py):

    scorer = SchemaScorer("schemas/dpia_schema.json")
    result = scorer.score(artifact)   # artifact = parsed JSON dict from raw output

ScoringResult.field_scores         dict[field_id, bool]  True = field present in artifact
ScoringResult.completeness_score   float                 fraction of *required* fields present (0–1)
ScoringResult.missing_required     list[str]             required field IDs absent from artifact
ScoringResult.missing_optional     list[str]             optional field IDs absent from artifact
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScoringResult:
    field_scores: dict[str, bool] = field(default_factory=dict)
    completeness_score: float = 0.0
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field_scores": self.field_scores,
            "completeness_score": self.completeness_score,
            "missing_required": self.missing_required,
            "missing_optional": self.missing_optional,
        }


class SchemaScorer:
    def __init__(self, schema_path: str | Path):
        with open(schema_path, encoding="utf-8") as fh:
            self.schema = json.load(fh)

    def score(self, artifact: dict) -> ScoringResult:
        """
        Score an artifact dict against the loaded schema.

        Args:
            artifact: parsed JSON output from the LLM (the 'parsed_fields' value
                      in a raw output record, or a fully parsed artifact dict)

        Returns:
            ScoringResult with per-field completeness and an overall score
        """
        raise NotImplementedError(
            "SchemaScorer.score() is not yet implemented. "
            "Finalize dpia_schema.json / aas_dpp_schema.json first."
        )

    def _flatten_fields(self) -> list[dict]:
        """Return a flat list of all leaf field dicts from the schema."""
        raise NotImplementedError
