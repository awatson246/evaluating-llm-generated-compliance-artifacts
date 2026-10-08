"""
Export aggregated results as LaTeX tables for the paper.

Tables generated
----------------
  Per task (GDPR / ESPR):
    1. Compliance completeness   — rows: vagueness level, cols: model  (mean [95% CI])
    2. Cross-run consistency     — same layout
    2b. Cross-run agreement      — same layout
    3. Required field inclusion  — rows: required fields, cols: model  (mean stability %)
    4. Significance              — pairwise vagueness comparisons per model

Usage:
    cd src
    python analysis/aggregate_results.py    # must run first
    python analysis/export_tables.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from analysis.labels import field_label, model_label  # noqa: E402

log = logging.getLogger(__name__)

OUTPUTS_DIR    = Path(__file__).parent.parent / "outputs"
AGGREGATE_CSV  = OUTPUTS_DIR / "aggregate_summary.csv"
FIELD_STAB_CSV = OUTPUTS_DIR / "field_stability.csv"
LATEX_OUT      = OUTPUTS_DIR / "latex_tables.tex"
SIG_CSV        = OUTPUTS_DIR / "significance_tests.csv"

VAGUENESS_ORDER  = ["baseline", "low", "medium", "high"]
VAGUENESS_LABELS = {"baseline": "Baseline", "low": "Low",
                    "medium": "Medium",   "high": "High"}


def _short_model(model_id: str) -> str:
    return model_label(model_id)


def _field_label(fid: str) -> str:
    return field_label(fid, latex=True)


# ── LaTeX helpers ─────────────────────────────────────────────────────────────

def latex_table(body_rows: list[str], header_row: str, col_spec: str,
                caption: str, label: str) -> str:
    body = "\n".join(body_rows)
    return (
        "\\begin{table}[t]\n"
        "  \\centering\n"
        f"  \\caption{{{caption}}}\n"
        f"  \\label{{{label}}}\n"
        f"  \\begin{{tabular}}{{{col_spec}}}\n"
        "    \\toprule\n"
        f"    {header_row} \\\\\n"
        "    \\midrule\n"
        f"{body}\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}"
    )


# ── Completeness and consistency tables ───────────────────────────────────────

def build_metric_table(df: pd.DataFrame, task: str,
                       metric_mean: str, ci_prefix: str,
                       caption: str, label: str) -> str:
    task_df  = df[df["task"] == task].copy()
    task_df["model_short"] = task_df["model_id"].apply(_short_model)

    models   = [m for m in task_df["model_short"].unique()]
    col_spec = "l" + "c" * len(models)
    header   = "Vagueness & " + " & ".join(models)

    rows = []
    for level in VAGUENESS_ORDER:
        sub = task_df[task_df["vagueness_level"] == level]
        if sub.empty:
            continue
        cells = []
        for model in models:
            row = sub[sub["model_short"] == model]
            if row.empty:
                cells.append("--")
            else:
                mu = row[metric_mean].iloc[0]
                lo = row[f"{ci_prefix}_ci_low"].iloc[0]  if f"{ci_prefix}_ci_low"  in row else float("nan")
                hi = row[f"{ci_prefix}_ci_high"].iloc[0] if f"{ci_prefix}_ci_high" in row else float("nan")
                if pd.isna(lo) or pd.isna(hi):
                    cells.append(f"{mu:.2f}")
                else:
                    cells.append(f"{mu:.2f} {{\\scriptsize [{lo:.2f}, {hi:.2f}]}}")
        rows.append(f"    {VAGUENESS_LABELS[level]} & " + " & ".join(cells) + " \\\\")

    return latex_table(rows, header, col_spec, caption, label)


# ── Field inclusion table ─────────────────────────────────────────────────────

def build_field_inclusion_table(field_df: pd.DataFrame, task: str,
                                caption: str, label: str) -> str:
    """
    Required fields (rows) × models (cols), cell = mean stability across all
    vagueness levels expressed as a percentage.
    """
    task_df = field_df[(field_df["task"] == task) & (field_df["required"])].copy()
    if task_df.empty:
        return ""

    task_df["model_short"] = task_df["model_id"].apply(_short_model)

    # Mean stability per (field_id, model) averaged over vagueness levels
    pivot = (
        task_df.groupby(["field_id", "model_short"])["field_stability"]
        .mean()
        .unstack("model_short")
    )

    models   = sorted(pivot.columns)
    col_spec = "l" + "c" * len(models)
    header   = "Required field & " + " & ".join(models)

    rows = []
    for fid in sorted(pivot.index):
        label_str = _field_label(fid)
        cells = []
        for model in models:
            val = pivot.loc[fid, model] if model in pivot.columns else float("nan")
            cells.append("--" if pd.isna(val) else f"{val * 100:.0f}\\%")
        rows.append(f"    {label_str} & " + " & ".join(cells) + " \\\\")

    return latex_table(rows, header, col_spec, caption, label)


# ── Significance table ────────────────────────────────────────────────────────

def build_significance_table(sig_df: pd.DataFrame, task: str,
                             caption: str, label: str) -> str:
    """Pairwise vagueness comparisons per model: Holm-adjusted p and Cliff's delta."""
    # Pairwise rows only; omnibus rows have an empty level_a ("" in memory, NaN from CSV)
    task_df = sig_df[(sig_df["task"] == task) & (sig_df["level_a"].fillna("") != "")].copy()
    if task_df.empty:
        return ""
    task_df["model_short"] = task_df["model_id"].apply(_short_model)

    rows = []
    for _, r in task_df.iterrows():
        a = VAGUENESS_LABELS.get(r["level_a"], r["level_a"])
        b = VAGUENESS_LABELS.get(r["level_b"], r["level_b"])
        p = r["p_holm"]
        p_str = "$<$0.001" if p < 0.001 else f"{p:.3f}"
        if p < 0.05:
            p_str = f"\\textbf{{{p_str}}}"
        rows.append(f"    {r['model_short']} & {a} vs {b} & {int(r['n_a'])}/{int(r['n_b'])} "
                    f"& {r['cliffs_delta']:+.2f} & {p_str} \\\\")

    header = "Model & Comparison & $n$ & Cliff's $\\delta$ & $p_{\\text{Holm}}$"
    return latex_table(rows, header, "llccc", caption, label)


# ── Main ──────────────────────────────────────────────────────────────────────

def export_tables(aggregate_csv: Path = AGGREGATE_CSV,
                  field_stab_csv: Path = FIELD_STAB_CSV) -> None:
    if not aggregate_csv.exists():
        log.error("Missing %s — run aggregate_results.py first", aggregate_csv)
        return
    if not field_stab_csv.exists():
        log.error("Missing %s — run aggregate_results.py first", field_stab_csv)
        return

    agg_df   = pd.read_csv(aggregate_csv)
    field_df = pd.read_csv(field_stab_csv)
    sig_df   = pd.read_csv(SIG_CSV) if SIG_CSV.exists() else None
    blocks: list[str] = []

    for task in sorted(agg_df["task"].unique()):
        tl = task.upper()

        blocks.append(build_metric_table(
            agg_df, task,
            metric_mean="mean_completeness",
            ci_prefix="completeness",
            caption=(f"Mean regulatory compliance (completeness) scores for {tl} "
                     f"artifacts by model and vagueness level "
                     f"(mean [95\\% bootstrap CI over runs])."),
            label=f"tab:{task}_completeness",
        ))

        # Consistency is group-level, so its CI comes from resampling runs.
        blocks.append(build_metric_table(
            agg_df, task,
            metric_mean="overall_consistency",
            ci_prefix="consistency",
            caption=(f"Cross-run consistency scores for {tl} "
                     f"artifacts by model and vagueness level "
                     f"(mean [95\\% bootstrap CI over runs])."),
            label=f"tab:{task}_consistency",
        ))

        if agg_df.loc[agg_df["task"] == task, "overall_agreement"].notna().any():
            blocks.append(build_metric_table(
                agg_df, task,
                metric_mean="overall_agreement",
                ci_prefix="agreement",
                caption=(f"Cross-run agreement for {tl} artifacts: fraction of run pairs "
                         f"making the same include/omit decision per field, averaged over "
                         f"fields (mean [95\\% bootstrap CI over runs])."),
                label=f"tab:{task}_agreement",
            ))

        inc_table = build_field_inclusion_table(
            field_df, task,
            caption=(f"Required field inclusion rates (\\%) for {tl} artifacts, "
                     f"averaged across all vagueness levels. "
                     f"Fields below 50\\% are systematically excluded."),
            label=f"tab:{task}_field_inclusion",
        )
        if inc_table:
            blocks.append(inc_table)

        if sig_df is not None:
            sig_table = build_significance_table(
                sig_df, task,
                caption=(f"Pairwise vagueness-level comparisons of {tl} completeness "
                         f"(two-sided Mann-Whitney $U$, Holm-corrected within each model). "
                         f"Bold: $p_{{\\text{{Holm}}}} < 0.05$."),
                label=f"tab:{task}_significance",
            )
            if sig_table:
                blocks.append(sig_table)

    output = "\n\n".join(blocks)
    LATEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    LATEX_OUT.write_text(output, encoding="utf-8")
    log.info("LaTeX tables -> %s", LATEX_OUT)
    print(output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    export_tables()
