"""
Compile scored outputs into a summary CSV for analysis and export.

Usage:
    cd research_pipeline
    python analysis/aggregate_results.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SCORED_DIR = Path(__file__).parent.parent / "outputs" / "scored"
OUT_PATH = Path(__file__).parent.parent / "outputs" / "aggregate_summary.csv"


def load_scored_outputs(scored_dir: Path = SCORED_DIR) -> list[dict]:
    paths = sorted(scored_dir.glob("*.json"))
    if not paths:
        log.warning("No scored outputs found in %s", scored_dir)
        return []
    records = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            records.append(json.load(fh))
    log.info("Loaded %d scored outputs", len(records))
    return records


def build_summary(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append({
            "model_id":            r.get("model_id"),
            "task":                r.get("task"),
            "vagueness_level":     r.get("vagueness_level"),
            "run_number":          r.get("run_number"),
            "completeness_score":  r.get("completeness_score", float("nan")),
            "overall_consistency": r.get("overall_consistency", float("nan")),
            "latency_seconds":     r.get("latency_seconds", float("nan")),
        })
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["model_id", "task", "vagueness_level"], sort=False)
        .agg(
            mean_completeness=("completeness_score",  "mean"),
            std_completeness= ("completeness_score",  "std"),
            mean_consistency= ("overall_consistency", "mean"),
            n_runs=           ("run_number",          "count"),
        )
        .reset_index()
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    records = load_scored_outputs()
    if not records:
        return
    df = build_summary(records)
    agg = aggregate(df)
    print(agg.to_string(index=False))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(OUT_PATH, index=False)
    log.info("Saved aggregate summary → %s", OUT_PATH)


if __name__ == "__main__":
    main()
