"""
Generate paper-ready figures from aggregated scoring results.

Figures produced (one set per task)
-------------------------------------
  completeness_<task>.pdf/png  — completeness by vagueness level, grouped by model
  consistency_<task>.pdf/png   — consistency by vagueness level, grouped by model
  field_heatmap_<task>.pdf/png — required field inclusion heatmap (fields × models)

Usage:
    cd src
    python analysis/aggregate_results.py    # must run first
    python analysis/plot_results.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend, safe for all environments
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

try:
    import seaborn as sns
    _HAS_SEABORN = True
except ImportError:
    _HAS_SEABORN = False

log = logging.getLogger(__name__)

OUTPUTS_DIR    = Path(__file__).parent.parent / "outputs"
AGGREGATE_CSV  = OUTPUTS_DIR / "aggregate_summary.csv"
FIELD_STAB_CSV = OUTPUTS_DIR / "field_stability.csv"
FIGURES_DIR    = OUTPUTS_DIR / "figures"

VAGUENESS_ORDER  = ["baseline", "low", "medium", "high"]
VAGUENESS_LABELS = {"baseline": "Baseline", "low": "Low",
                    "medium": "Medium",   "high": "High"}

MODEL_SHORT: dict[str, str] = {
    "gpt-4o":                    "GPT-4o",
    "claude-sonnet-4-6":         "Claude",
    "Llama-3.1-8B-Instruct":    "Llama-3.1",
    "Mistral-7B-Instruct-v0.2": "Mistral",
    "Qwen2.5-7B-Instruct":      "Qwen-2.5",
}

FIELD_LABELS: dict[str, str] = {
    "processing_description.nature":                           "Nature of processing",
    "processing_description.scope.data_categories":           "Data categories",
    "processing_description.scope.retention_period":          "Retention period",
    "processing_description.purposes.stated_purposes":        "Processing purposes",
    "processing_description.data_subjects.categories":        "Data subject categories",
    "processing_description.actors":                          "Controllers & processors",
    "necessity_proportionality.lawful_basis":                 "Lawful basis (Art. 6)",
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
    "product_identification.manufacturer":   "Manufacturer",
    "product_identification.brand":          "Brand",
    "product_identification.model":          "Model designation",
    "product_identification.country_of_origin": "Country of origin",
    "product_classification.product_category": "Product category",
    "material_composition.materials":        "Materials list",
    "material_composition.recycled_content": "Recycled content %",
    "material_composition.substances_of_concern": "SVHC declaration",
    "material_composition.hazardous_materials": "Hazardous materials",
    "carbon_footprint.lifecycle_co2":        "Lifecycle CO₂",
    "carbon_footprint.methodology":          "Calculation methodology",
    "circularity.repairability_score":       "Repairability score",
    "circularity.recyclability_rate":        "Recyclability rate",
    "circularity.spare_parts_availability":  "Spare parts availability",
    "circularity.end_of_life_instructions":  "End-of-life instructions",
    "compliance.ce_marking":                 "CE marking",
    "compliance.eu_declarations":            "EU declaration of conformity",
    "compliance.reach_compliance":           "REACH compliance",
}

# Colorblind-friendly palette (Okabe-Ito)
_PALETTE = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
            "#D55E00", "#CC79A7", "#000000"]


def _short_model(model_id: str) -> str:
    base = model_id.split("/")[-1]
    return MODEL_SHORT.get(base, MODEL_SHORT.get(model_id, base))


def _field_label(fid: str) -> str:
    return FIELD_LABELS.get(fid, fid.split(".")[-1].replace("_", " ").title())


def _savefig(fig: plt.Figure, stem: str) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        path = FIGURES_DIR / f"{stem}.{ext}"
        fig.savefig(path, bbox_inches="tight", dpi=300)
        log.info("Saved %s", path)
    plt.close(fig)


def _paper_style() -> None:
    plt.rcParams.update({
        "font.family":       "sans-serif",
        "font.size":         9,
        "axes.titlesize":    10,
        "axes.labelsize":    9,
        "xtick.labelsize":   8,
        "ytick.labelsize":   8,
        "legend.fontsize":   8,
        "figure.dpi":        150,
        "axes.spines.top":   False,
        "axes.spines.right": False,
    })


# ── Figure 1 & 2: Bar charts (completeness / consistency) ─────────────────────

def plot_metric_bars(agg_df: pd.DataFrame, task: str,
                     metric: str, ylabel: str,
                     title: str, stem: str) -> None:
    """
    Grouped bar chart: x = vagueness level, groups = models.
    Error bars show std (completeness only; consistency is group-level).
    """
    task_df = agg_df[agg_df["task"] == task].copy()
    task_df["model_short"] = task_df["model_id"].apply(_short_model)

    models   = task_df["model_short"].unique().tolist()
    levels   = [lv for lv in VAGUENESS_ORDER if lv in task_df["vagueness_level"].values]
    n_models = len(models)
    n_levels = len(levels)

    x      = np.arange(n_levels)
    width  = 0.8 / n_models
    offset = np.linspace(-(n_models - 1) / 2, (n_models - 1) / 2, n_models) * width

    fig, ax = plt.subplots(figsize=(5.5, 3.2))

    for i, model in enumerate(models):
        mdf    = task_df[task_df["model_short"] == model]
        values = []
        errors = []
        for lv in levels:
            row = mdf[mdf["vagueness_level"] == lv]
            if row.empty:
                values.append(0.0)
                errors.append(0.0)
            else:
                values.append(float(row[metric].iloc[0]))
                std_col = "std_completeness" if metric == "mean_completeness" else None
                errors.append(float(row[std_col].iloc[0])
                              if std_col and not pd.isna(row[std_col].iloc[0]) else 0.0)

        ax.bar(x + offset[i], values, width,
               label=model,
               color=_PALETTE[i % len(_PALETTE)],
               yerr=errors if any(e > 0 for e in errors) else None,
               capsize=2, error_kw={"linewidth": 0.8})

    ax.set_xticks(x)
    ax.set_xticklabels([VAGUENESS_LABELS[lv] for lv in levels])
    ax.set_xlabel("Context")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_title(title)
    ax.legend(loc="lower right", ncol=2, framealpha=0.9)
    ax.axhline(1.0, color="grey", linewidth=0.5, linestyle="--")

    _savefig(fig, stem)


# ── Figure 3: Field inclusion heatmap ─────────────────────────────────────────

def plot_field_heatmap(field_df: pd.DataFrame, task: str) -> None:
    """
    Heatmap: required fields (rows) × models (cols).
    Cell value = mean field_stability across all vagueness levels.
    Annotated with percentages; rows sorted descending by mean inclusion.
    """
    task_df = field_df[(field_df["task"] == task) & (field_df["required"])].copy()
    if task_df.empty:
        log.warning("No required-field stability data for task '%s'", task)
        return

    task_df["model_short"] = task_df["model_id"].apply(_short_model)
    task_df["field_label"] = task_df["field_id"].apply(_field_label)

    pivot = (
        task_df.groupby(["field_label", "model_short"])["field_stability"]
        .mean()
        .unstack("model_short")
    )
    # Sort rows: lowest mean inclusion first (most problematic at top)
    pivot = pivot.loc[pivot.mean(axis=1).sort_values().index]

    n_fields = len(pivot)
    n_models = len(pivot.columns)
    fig_h    = max(3.5, n_fields * 0.38)
    fig, ax  = plt.subplots(figsize=(max(4.0, n_models * 1.2), fig_h))

    data = pivot.values  # shape (n_fields, n_models)

    # Draw heatmap manually if seaborn unavailable
    if _HAS_SEABORN:
        sns.heatmap(
            pivot, ax=ax, vmin=0, vmax=1,
            cmap="YlOrRd_r",
            annot=True, fmt=".0%",
            annot_kws={"size": 7},
            linewidths=0.4, linecolor="white",
            cbar_kws={"label": "Inclusion rate", "shrink": 0.7},
        )
    else:
        im = ax.imshow(data, vmin=0, vmax=1, cmap="YlOrRd_r", aspect="auto")
        plt.colorbar(im, ax=ax, label="Inclusion rate", shrink=0.7)
        for r in range(n_fields):
            for c in range(n_models):
                val = data[r, c]
                color = "black" if val > 0.5 else "white"
                ax.text(c, r, f"{val:.0%}", ha="center", va="center",
                        fontsize=7, color=color)
        ax.set_xticks(range(n_models))
        ax.set_xticklabels(pivot.columns, rotation=30, ha="right")
        ax.set_yticks(range(n_fields))
        ax.set_yticklabels(pivot.index)

    ax.set_title(f"{task.upper()} — Required field inclusion by model\n"
                 f"(mean across vagueness levels; sorted by lowest inclusion)")
    ax.set_xlabel("Model")
    ax.set_ylabel("")
    fig.tight_layout()

    _savefig(fig, f"field_heatmap_{task}")


# ── Figure 4: Completeness vs. consistency scatter ────────────────────────────

def plot_completeness_vs_consistency(agg_df: pd.DataFrame, task: str) -> None:
    """
    Scatter: x = overall_consistency, y = group_completeness.
    Each point is one (model, vagueness_level) condition.
    """
    task_df = agg_df[agg_df["task"] == task].copy()
    task_df["model_short"] = task_df["model_id"].apply(_short_model)
    models   = task_df["model_short"].unique().tolist()
    markers  = ["o", "s", "^", "D", "v", "P"]
    level_colors = {
        "baseline": "#333333",
        "low":      "#2166AC",
        "medium":   "#F4A582",
        "high":     "#D6604D",
    }

    fig, ax = plt.subplots(figsize=(4.2, 3.5))

    for i, model in enumerate(models):
        mdf = task_df[task_df["model_short"] == model]
        for _, row in mdf.iterrows():
            lvl = row["vagueness_level"]
            ax.scatter(row["overall_consistency"],
                       row["group_completeness"],
                       marker=markers[i % len(markers)],
                       color=level_colors.get(lvl, "grey"),
                       s=55, zorder=3)

    # Legend: models (shape) and levels (colour)
    shape_handles = [
        mpatches.Patch(facecolor="grey", label=m)
        for m, mk in zip(models, markers[:len(models)])
    ]
    # Use scatter proxies for marker shapes
    shape_handles = [
        plt.Line2D([0], [0], marker=markers[i % len(markers)],
                   color="w", markerfacecolor="grey",
                   markersize=6, label=model)
        for i, model in enumerate(models)
    ]
    color_handles = [
        mpatches.Patch(facecolor=c, label=VAGUENESS_LABELS.get(lv, lv))
        for lv, c in level_colors.items()
        if lv in task_df["vagueness_level"].values
    ]
    leg1 = ax.legend(handles=shape_handles, loc="lower right",
                     title="Model", fontsize=7, title_fontsize=7)
    ax.add_artist(leg1)
    ax.legend(handles=color_handles, loc="upper left",
              title="Vagueness", fontsize=7, title_fontsize=7)

    ax.set_xlabel("Consistency score")
    ax.set_ylabel("Group completeness score")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(f"{task.upper()} — Completeness vs. Consistency")
    ax.plot([0, 1], [0, 1], "k--", linewidth=0.5, alpha=0.3)

    _savefig(fig, f"completeness_vs_consistency_{task}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    _paper_style()

    for csv in (AGGREGATE_CSV, FIELD_STAB_CSV):
        if not csv.exists():
            log.error("Missing %s — run aggregate_results.py first", csv)
            return

    agg_df   = pd.read_csv(AGGREGATE_CSV)
    field_df = pd.read_csv(FIELD_STAB_CSV)

    for task in sorted(agg_df["task"].unique()):
        tl = task.upper()
        log.info("Plotting task: %s", tl)

        plot_metric_bars(
            agg_df, task,
            metric="mean_completeness",
            ylabel="Mean completeness score",
            title=f"{tl} — Regulatory Compliance by Vagueness Level",
            stem=f"completeness_{task}",
        )
        plot_metric_bars(
            agg_df, task,
            metric="overall_consistency",
            ylabel="Consistency score",
            title=f"{tl} — Cross-run Consistency by Vagueness Level",
            stem=f"consistency_{task}",
        )
        plot_field_heatmap(field_df, task)
        plot_completeness_vs_consistency(agg_df, task)

    log.info("All figures saved to %s", FIGURES_DIR)


if __name__ == "__main__":
    main()
