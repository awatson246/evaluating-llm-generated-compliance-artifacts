"""
Export aggregated results as LaTeX tables ready for an AAAI-style paper.

Tables are structured as:
  - Rows: vagueness levels (low / medium / high)
  - Columns: models
  - Cells: mean completeness score  OR  mean consistency score

One pair of tables (completeness + consistency) is generated per task.

Usage:
    cd research_pipeline
    python analysis/aggregate_results.py   # must run first
    python analysis/export_tables.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

OUTPUTS_DIR   = Path(__file__).parent.parent / "outputs"
SUMMARY_CSV   = OUTPUTS_DIR / "aggregate_summary.csv"
LATEX_OUT     = OUTPUTS_DIR / "latex_tables.tex"

VAGUENESS_ORDER  = ["low", "medium", "high"]
VAGUENESS_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


def _short_model(model_id: str) -> str:
    return model_id.split("/")[-1]


def build_pivot(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    pivot = df.pivot_table(
        index="vagueness_level",
        columns="model_id",
        values=metric,
        aggfunc="mean",
    ).reindex(VAGUENESS_ORDER)
    pivot.columns = [_short_model(c) for c in pivot.columns]
    return pivot


def to_latex_table(pivot: pd.DataFrame, caption: str, label: str) -> str:
    n_cols   = len(pivot.columns)
    col_spec = "l" + "c" * n_cols
    headers  = " & ".join(pivot.columns)

    row_lines = []
    for level in VAGUENESS_ORDER:
        if level not in pivot.index:
            continue
        cells = " & ".join(
            f"{pivot.loc[level, col]:.3f}" if pd.notna(pivot.loc[level, col]) else "--"
            for col in pivot.columns
        )
        row_lines.append(f"    {VAGUENESS_LABELS[level]} & {cells} \\\\")

    body = "\n".join(row_lines)
    return (
        f"\\begin{{table}}[t]\n"
        f"  \\centering\n"
        f"  \\caption{{{caption}}}\n"
        f"  \\label{{{label}}}\n"
        f"  \\begin{{tabular}}{{{col_spec}}}\n"
        f"    \\toprule\n"
        f"    Vagueness & {headers} \\\\\n"
        f"    \\midrule\n"
        f"{body}\n"
        f"    \\bottomrule\n"
        f"  \\end{{tabular}}\n"
        f"\\end{{table}}"
    )


def export_tables(summary_csv: Path = SUMMARY_CSV) -> None:
    if not summary_csv.exists():
        log.error("Aggregate summary not found at %s — run aggregate_results.py first", summary_csv)
        return

    df = pd.read_csv(summary_csv)
    blocks: list[str] = []

    for task in sorted(df["task"].unique()):
        task_df  = df[df["task"] == task]
        task_label = task.upper()

        pivot_c = build_pivot(task_df, "mean_completeness")
        blocks.append(to_latex_table(
            pivot_c,
            caption=f"Mean field completeness scores for {task_label} artifacts by model and vagueness level.",
            label=f"tab:{task}_completeness",
        ))

        pivot_k = build_pivot(task_df, "mean_consistency")
        blocks.append(to_latex_table(
            pivot_k,
            caption=f"Mean cross-run consistency scores for {task_label} artifacts by model and vagueness level.",
            label=f"tab:{task}_consistency",
        ))

    latex_output = "\n\n".join(blocks)
    LATEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    LATEX_OUT.write_text(latex_output, encoding="utf-8")
    log.info("LaTeX tables written → %s", LATEX_OUT)
    print(latex_output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    export_tables()
