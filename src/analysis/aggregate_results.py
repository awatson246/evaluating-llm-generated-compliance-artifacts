"""
Compile scored outputs into summary CSVs for downstream table and figure generation.

Outputs
-------
  outputs/aggregate_summary.csv   per-(model, task, vagueness_level) metrics
  outputs/field_stability.csv     per-(model, task, vagueness_level, field_id) stability
  outputs/significance_tests.csv  vagueness-level comparisons per (model, task)

Usage:
    cd src
    python analysis/aggregate_results.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from scoring.schema_scorer import SchemaScorer  # noqa: E402
from analysis.statistics import SIG_CSV, bootstrap_cis, significance_tests  # noqa: E402

log = logging.getLogger(__name__)

SCORED_DIR     = ROOT / "outputs" / "scored"
SCHEMAS_DIR    = ROOT / "schemas"
AGGREGATE_CSV  = ROOT / "outputs" / "aggregate_summary.csv"
FIELD_STAB_CSV = ROOT / "outputs" / "field_stability.csv"

_SCHEMA_MAP = {
    "gdpr": SCHEMAS_DIR / "dpia_schema.json",
    "espr": SCHEMAS_DIR / "aas_dpp_schema.json",
}

# Cache SchemaScorer instances to avoid re-loading
_scorer_cache: dict[str, SchemaScorer] = {}


def _required_ids(task: str) -> set[str]:
    if task not in _scorer_cache:
        sp = _SCHEMA_MAP.get(task)
        if sp and sp.exists():
            _scorer_cache[task] = SchemaScorer(sp)
    scorer = _scorer_cache.get(task)
    return {f.id for f in scorer._fields if f.required} if scorer else set()


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_scored_outputs(scored_dir: Path = SCORED_DIR) -> list[dict]:
    paths = sorted(scored_dir.glob("*.json"))
    if not paths:
        log.warning("No scored outputs found in %s", scored_dir)
        return []
    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    log.info("Loaded %d scored output(s)", len(records))
    return records


# ── Summary builders ──────────────────────────────────────────────────────────

def build_per_run_summary(records: list[dict]) -> pd.DataFrame:
    """One row per individual run."""
    rows = []
    for r in records:
        rows.append({
            "model_id":            r.get("model_id"),
            "task":                r.get("task"),
            "vagueness_level":     r.get("vagueness_level"),
            "run_number":          r.get("run_number"),
            "completeness_score":  r.get("completeness_score",      float("nan")),
            "group_completeness":  r.get("group_completeness_score", float("nan")),
            "overall_consistency": r.get("overall_consistency",      float("nan")),
            "overall_agreement":   r.get("overall_agreement",        float("nan")),
            "latency_seconds":     r.get("latency_seconds",          float("nan")),
        })
    return pd.DataFrame(rows)


def build_field_stability(records: list[dict]) -> pd.DataFrame:
    """
    One row per (model, task, vagueness_level, field_id).
    field_stability is a group-level metric so we take the first run per group.
    """
    seen: set[tuple] = set()
    rows = []
    for r in records:
        key = (r.get("model_id"), r.get("task"), r.get("vagueness_level"))
        if key in seen:
            continue
        seen.add(key)
        task         = r.get("task", "")
        required_ids = _required_ids(task)
        for fid, stab in r.get("field_stability", {}).items():
            rows.append({
                "model_id":        r.get("model_id"),
                "task":            task,
                "vagueness_level": r.get("vagueness_level"),
                "field_id":        fid,
                "field_stability": stab,
                "required":        fid in required_ids,
            })
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse per-run rows to per-(model, task, vagueness_level) group stats.
    group_completeness, overall_consistency and overall_agreement are group-level values stored
    identically on every run in the group, so we just take the first.
    """
    per_run = (
        df.groupby(["model_id", "task", "vagueness_level"], sort=False)
        .agg(
            mean_completeness=("completeness_score", "mean"),
            std_completeness= ("completeness_score", "std"),
            n_runs=           ("run_number",         "count"),
        )
        .reset_index()
    )
    group_lvl = (
        df.groupby(["model_id", "task", "vagueness_level"], sort=False)
        .first()[["group_completeness", "overall_consistency", "overall_agreement"]]
        .reset_index()
    )
    return per_run.merge(group_lvl, on=["model_id", "task", "vagueness_level"])


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    records = load_scored_outputs()
    if not records:
        return
    if any("overall_agreement" not in r for r in records):
        log.warning("Some scored outputs predate the agreement metric - "
                    "re-run run_scoring.py to populate overall_agreement")

    per_run   = build_per_run_summary(records)
    agg       = aggregate(per_run).merge(
        bootstrap_cis(records), on=["model_id", "task", "vagueness_level"], how="left")
    field_stab = build_field_stability(records)
    sig       = significance_tests(per_run, level_order=["baseline", "low", "medium", "high"])

    AGGREGATE_CSV.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(AGGREGATE_CSV, index=False)
    log.info("Saved -> %s", AGGREGATE_CSV)

    field_stab.to_csv(FIELD_STAB_CSV, index=False)
    log.info("Saved -> %s", FIELD_STAB_CSV)

    sig.to_csv(SIG_CSV, index=False)
    log.info("Saved -> %s", SIG_CSV)

    for task, sub in agg.groupby("task"):
        counts = sorted(sub["n_runs"].unique())
        if len(counts) > 1:
            log.warning("Task %s has unequal run counts across conditions: %s", task, counts)

    print(agg.to_string(index=False))


if __name__ == "__main__":
    main()
