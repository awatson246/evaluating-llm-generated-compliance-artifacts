"""
Export aggregated results as LaTeX tables for the paper.

Tables generated
----------------
  Per task (GDPR / ESPR):
    1. Compliance completeness   — rows: vagueness level, cols: model  (mean ± std)
    2. Cross-run consistency     — same layout
    3. Required field inclusion  — rows: required fields, cols: model  (mean stability %)

Usage:
    cd src
    python analysis/aggregate_results.py    # must run first
    python analysis/export_tables.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

OUTPUTS_DIR    = Path(__file__).parent.parent / "outputs"
AGGREGATE_CSV  = OUTPUTS_DIR / "aggregate_summary.csv"
FIELD_STAB_CSV = OUTPUTS_DIR / "field_stability.csv"
LATEX_OUT      = OUTPUTS_DIR / "latex_tables.tex"

VAGUENESS_ORDER  = ["baseline", "low", "medium", "high"]
VAGUENESS_LABELS = {"baseline": "Baseline", "low": "Low",
                    "medium": "Medium",   "high": "High"}

# Display names for models (last path segment → short label)
MODEL_SHORT: dict[str, str] = {
    "gpt-4o":                               "GPT-4o",
    "claude-sonnet-4-6":                    "Claude",
    "Llama-3.1-8B-Instruct":               "Llama-3.1",
    "open-mistral-7b":                     "Mistral-7B",
    "Qwen2.5-7B-Instruct":                 "Qwen-2.5",
}

# Human-readable field labels for the inclusion table
FIELD_LABELS: dict[str, str] = {
    "processing_description.nature":                           "Nature of processing",
    "processing_description.scope.data_categories":           "Data categories",
    "processing_description.scope.retention_period":          "Retention period",
    "processing_description.purposes.stated_purposes":        "Processing purposes",
    "processing_description.data_subjects.categories":        "Data subject categories",
    "processing_description.actors":                          "Controllers \\& processors",
    "necessity_proportionality.lawful_basis":                 "Lawful basis (Art.~6)",
    "necessity_proportionality.necessity_justification":      "Necessity justification",
    "necessity_proportionality.proportionality_justification":"Proportionality",
    "necessity_proportionality.data_minimisation":            "Data minimisation",
    "necessity_proportionality.storage_limitation":           "Storage limitation",
    "necessity_proportionality.data_subject_rights":          "Data subject rights",
    "risk_assessment.identified_risks":                       "Identified risks",
    "risk_assessment.risk_likelihood":                        "Risk likelihood",
    "risk_assessment.risk_severity":                          "Risk severity",
    "risk_assessment.residual_risk":                          "Residual risk",
    "risk_mitigation.technical_measures":                     "Technical measures",
    "risk_mitigation.organisational_measures":                "Organisational measures",
    "risk_mitigation.compliance_mechanisms":                  "Compliance mechanisms",
    # AAS fields
    "product_identification.manufacturer":   "Manufacturer",
    "product_identification.brand":          "Brand",
    "product_identification.model":          "Model designation",
    "product_identification.country_of_origin": "Country of origin",
    "product_classification.product_category": "Product category",
    "material_composition.materials":        "Materials list",
    "material_composition.recycled_content": "Recycled content \\%",
    "material_composition.substances_of_concern": "SVHC declaration",
    "material_composition.hazardous_materials": "Hazardous materials",
    "carbon_footprint.lifecycle_co2":        "Lifecycle CO\\textsubscript{2}",
    "carbon_footprint.methodology":          "Calculation methodology",
    "circularity.repairability_score":       "Repairability score",
    "circularity.recyclability_rate":        "Recyclability rate",
    "circularity.spare_parts_availability":  "Spare parts availability",
    "circularity.end_of_life_instructions":  "End-of-life instructions",
    "compliance.ce_marking":                 "CE marking",
    "compliance.eu_declarations":            "EU declaration of conformity",
    "compliance.reach_compliance":           "REACH compliance",
}


def _short_model(model_id: str) -> str:
    base = model_id.split("/")[-1]
    return MODEL_SHORT.get(base, MODEL_SHORT.get(model_id, base))


def _field_label(fid: str) -> str:
    return FIELD_LABELS.get(fid, fid.split(".")[-1].replace("_", " ").title())


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
                       metric_mean: str, metric_std: str,
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
                mu  = row[metric_mean].iloc[0]
                std = row[metric_std].iloc[0]
                if pd.isna(std):
                    cells.append(f"{mu:.2f}")
                else:
                    cells.append(f"{mu:.2f}$\\pm${std:.2f}")
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
    blocks: list[str] = []

    for task in sorted(agg_df["task"].unique()):
        tl = task.upper()

        blocks.append(build_metric_table(
            agg_df, task,
            metric_mean="mean_completeness",
            metric_std="std_completeness",
            caption=(f"Mean regulatory compliance (completeness) scores for {tl} "
                     f"artifacts by model and vagueness level (mean $\\pm$ std)."),
            label=f"tab:{task}_completeness",
        ))

        # Consistency: group-level value is the same for all runs so std is 0;
        # present as a plain mean without ± to avoid misleading zeros.
        agg_df["_cons_std"] = float("nan")
        blocks.append(build_metric_table(
            agg_df, task,
            metric_mean="overall_consistency",
            metric_std="_cons_std",
            caption=(f"Cross-run consistency scores for {tl} "
                     f"artifacts by model and vagueness level."),
            label=f"tab:{task}_consistency",
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

    output = "\n\n".join(blocks)
    LATEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    LATEX_OUT.write_text(output, encoding="utf-8")
    log.info("LaTeX tables -> %s", LATEX_OUT)
    print(output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    export_tables()
