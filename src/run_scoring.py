"""
Scoring orchestrator: reads raw outputs, applies schema + consistency scoring,
writes per-run scored records to outputs/scored/, and prints a field-inclusion
summary for each (task, model, vagueness_level) group.

Usage:
    cd src
    python run_scoring.py                   # score everything in outputs/raw/
    python run_scoring.py --task gdpr       # score only GDPR outputs
    python run_scoring.py --task espr
    python run_scoring.py --config path/to/other_config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

from scoring import ConsistencyScorer, SchemaScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT        = Path(__file__).parent
OUTPUTS_RAW = ROOT / "outputs" / "raw"
OUTPUTS_SCO = ROOT / "outputs" / "scored"
SCHEMAS_DIR = ROOT / "schemas"

_SCHEMA_MAP = {
    "gdpr": SCHEMAS_DIR / "dpia_schema.json",
    "espr": SCHEMAS_DIR / "aas_dpp_schema.json",
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_raw_outputs(task_filter: str | None = None) -> list[dict]:
    records = []
    for p in sorted(OUTPUTS_RAW.glob("*.json")):
        with open(p, encoding="utf-8") as fh:
            rec = json.load(fh)
        if task_filter and rec.get("task") != task_filter:
            continue
        records.append(rec)
    log.info("Loaded %d raw output(s)", len(records))
    return records


def save_scored(record: dict) -> None:
    OUTPUTS_SCO.mkdir(parents=True, exist_ok=True)
    safe_model = record["model_id"].replace("/", "_")
    ts         = record["timestamp"].replace(":", "-").replace("+", "")
    filename   = f"{safe_model}__{record['task']}__{record['vagueness_level']}__run{record['run_number']}__{ts}.json"
    out        = OUTPUTS_SCO / filename
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    log.info("Saved  %s", out.name)


# ── Scoring ───────────────────────────────────────────────────────────────────

def group_records(records: list[dict]) -> dict[tuple, list[dict]]:
    """Return records keyed by (model_id, task, vagueness_level)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in records:
        key = (rec["model_id"], rec["task"], rec["vagueness_level"])
        groups[key].append(rec)
    return dict(groups)


def score_all(records: list[dict], stability_threshold: float = 1.0) -> list[dict]:
    """
    For each (model, task, level) group:
      1. Score each run individually (schema completeness).
      2. Score the union of all runs in the group (combined completeness).
      3. Compute consistency across runs.
      4. Attach scores to each run's record and return them all.
    """
    groups = group_records(records)
    scored_records: list[dict] = []

    for (model_id, task, level), group in sorted(groups.items()):
        schema_path = _SCHEMA_MAP.get(task)
        if schema_path is None:
            log.warning("No schema for task '%s' — skipping group (%s, %s, %s)",
                        task, model_id, task, level)
            continue
        if not schema_path.exists():
            log.error("Schema file not found: %s — skipping group (%s, %s, %s)",
                      schema_path, model_id, task, level)
            continue

        log.info("Scoring  %-40s  task=%-5s  level=%-8s  (%d run(s))",
                 model_id, task, level, len(group))

        schema_scorer = SchemaScorer(schema_path)
        consistency_scorer = ConsistencyScorer(stability_threshold=stability_threshold)

        # Per-run schema scores
        per_run_results = [
            schema_scorer.score(rec["raw_response"]) for rec in group
        ]

        # Group-level (union) compliance score
        group_result = schema_scorer.score_group([rec["raw_response"] for rec in group])

        # Consistency across runs
        consistency_result = consistency_scorer.score(
            [r.to_dict() for r in per_run_results]
        )

        for rec, run_result in zip(group, per_run_results):
            scored = dict(rec)  # shallow copy — don't mutate original
            scored["completeness_score"]        = run_result.completeness_score
            scored["missing_required"]          = run_result.missing_required
            scored["missing_optional"]          = run_result.missing_optional
            scored["field_scores"]              = run_result.field_scores
            scored["group_completeness_score"]  = group_result.completeness_score
            scored["group_missing_required"]    = group_result.missing_required
            scored["overall_consistency"]       = consistency_result.overall_consistency
            scored["field_stability"]           = consistency_result.field_stability
            scored["stable_fields"]             = consistency_result.stable_fields
            scored["unstable_fields"]           = consistency_result.unstable_fields
            scored_records.append(scored)

    return scored_records


# ── Field-inclusion summary ───────────────────────────────────────────────────

def print_field_inclusion_summary(scored_records: list[dict]) -> None:
    """
    For each task × field, show what fraction of (model, level) groups included
    that field in their group-union score.  Highlights commonly excluded fields.
    """
    # Collect group-level field_scores (use first run per group; all carry same group scores)
    seen: set[tuple] = set()
    group_field_scores: dict[str, list[dict[str, bool]]] = defaultdict(list)

    for rec in scored_records:
        key = (rec["model_id"], rec["task"], rec["vagueness_level"])
        if key in seen:
            continue
        seen.add(key)
        # field_scores here are per-run; use group union via the group_missing_required list
        # We reconstruct a binary group score from group_missing_required
        all_fields = set(rec.get("field_scores", {}).keys())
        missing    = set(rec.get("group_missing_required", []))
        group_scores = {fid: (fid not in missing) for fid in all_fields}
        group_field_scores[rec["task"]].append(group_scores)

    for task, all_groups in sorted(group_field_scores.items()):
        if not all_groups:
            continue
        all_field_ids = sorted({fid for g in all_groups for fid in g})
        n = len(all_groups)
        print(f"\n{'-'*70}")
        print(f"  Field inclusion summary - task: {task.upper()}  ({n} condition groups)")
        print(f"{'-'*70}")
        print(f"  {'Field ID':<55}  {'Included':>8}")
        print(f"  {'-'*55}  {'-'*8}")
        for fid in all_field_ids:
            frac = sum(g.get(fid, False) for g in all_groups) / n
            marker = "  <<" if frac < 0.5 else ""
            print(f"  {fid:<55}  {frac:>7.0%}{marker}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score raw LLM outputs for schema compliance and consistency."
    )
    parser.add_argument(
        "--task", choices=list(_SCHEMA_MAP.keys()),
        help="Score only this task (default: all tasks)."
    )
    parser.add_argument(
        "--stability-threshold", type=float, default=1.0,
        help="Minimum fraction of runs a field must appear in to be called stable (default: 1.0)."
    )
    args = parser.parse_args()

    records = load_raw_outputs(task_filter=args.task)
    if not records:
        log.warning("No raw outputs to score.")
        return

    scored = score_all(records, stability_threshold=args.stability_threshold)
    for rec in scored:
        save_scored(rec)

    log.info("Scoring complete — %d record(s) written to %s", len(scored), OUTPUTS_SCO)
    print_field_inclusion_summary(scored)


if __name__ == "__main__":
    main()
