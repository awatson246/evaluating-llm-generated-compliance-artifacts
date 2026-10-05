"""
Inferential statistics over scored runs.

Two things the per-condition mean ± std summary cannot provide:

  1. Uncertainty on every metric, including group-level ones.
     overall_consistency and overall_agreement are computed once per condition
     from all of its runs, so they have no per-run spread. Percentile bootstrap CIs resample runs with
     replacement and recompute each metric on the resample, which gives an
     interval for completeness and consistency alike.

  2. Tests of whether vagueness level changes a model's completeness.
     Per (model, task): Kruskal-Wallis across all levels, then pairwise
     Mann-Whitney U with Holm correction within that (model, task) family,
     reported with Cliff's delta as the effect size. Rank-based tests are used
     because completeness is bounded and frequently at ceiling.

Outputs
-------
  outputs/significance_tests.csv   one row per (model, task, comparison)

Usage:
    cd src
    python analysis/aggregate_results.py    # also writes CI columns
    python analysis/statistics.py           # significance tests only
"""

from __future__ import annotations

import itertools
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from scoring.consistency_scorer import pairwise_agreement  # noqa: E402

log = logging.getLogger(__name__)

SIG_CSV = ROOT / "outputs" / "significance_tests.csv"

N_BOOT     = 10_000
CI_LEVEL   = 0.95
SEED       = 0
GROUP_KEYS = ("model_id", "task", "vagueness_level")


# ── Bootstrap CIs ─────────────────────────────────────────────────────────────

def _field_matrix(group: list[dict]) -> np.ndarray:
    """runs × fields boolean matrix over the union of fields seen in the group."""
    field_ids = sorted({fid for r in group for fid in r.get("field_scores", {})})
    return np.array([
        [bool(r.get("field_scores", {}).get(fid, False)) for fid in field_ids]
        for r in group
    ], dtype=float)


def bootstrap_group(group: list[dict], n_boot: int = N_BOOT,
                    ci: float = CI_LEVEL, seed: int = SEED) -> dict[str, float]:
    """
    Percentile bootstrap CIs for one condition's mean completeness, overall
    consistency and overall agreement (as defined in ConsistencyScorer).
    The agreement interval is bias-corrected; see below.
    """
    rng   = np.random.default_rng(seed)
    comp  = np.array([r.get("completeness_score", np.nan) for r in group], dtype=float)
    mat   = _field_matrix(group)
    n     = len(group)
    idx   = rng.integers(0, n, size=(n_boot, n))

    boot_comp = np.nanmean(comp[idx], axis=1)
    # Mean over fields of per-field stability == mean over runs of each run's
    # fraction of fields present (the field set is fixed), so resample those.
    run_frac  = mat.mean(axis=1) if mat.size else np.full(n, np.nan)
    boot_cons = run_frac[idx].mean(axis=1)

    # Agreement depends on per-field inclusion counts, so resample each field's
    # column separately (n_boot x n per field keeps memory flat as runs grow).
    agree = np.vectorize(pairwise_agreement, otypes=[float])
    if mat.size and n >= 2:
        boot_agree = np.mean(
            [agree(mat[:, j][idx].sum(axis=1).astype(int), n) for j in range(mat.shape[1])],
            axis=0,
        )
        # Resampling with replacement duplicates runs, and a duplicated run always
        # agrees with itself, so the bootstrap distribution sits above the estimate
        # (badly so at small n). Re-centre it on the point estimate before taking
        # percentiles (bias-corrected percentile interval).
        point = np.mean(agree(mat.sum(axis=0).astype(int), n))
        boot_agree = np.clip(boot_agree - (boot_agree.mean() - point), 0.0, 1.0)
    else:
        boot_agree = np.full(n_boot, np.nan)

    lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
    return {
        "completeness_ci_low":  float(np.percentile(boot_comp, lo)),
        "completeness_ci_high": float(np.percentile(boot_comp, hi)),
        "consistency_ci_low":   float(np.percentile(boot_cons, lo)),
        "consistency_ci_high":  float(np.percentile(boot_cons, hi)),
        "agreement_ci_low":     float(np.percentile(boot_agree, lo)),
        "agreement_ci_high":    float(np.percentile(boot_agree, hi)),
    }


def bootstrap_cis(records: list[dict], **kwargs) -> pd.DataFrame:
    """One row of CI bounds per (model, task, vagueness_level)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[tuple(r.get(k) for k in GROUP_KEYS)].append(r)
    rows = [
        dict(zip(GROUP_KEYS, key), **bootstrap_group(group, **kwargs))
        for key, group in groups.items()
    ]
    return pd.DataFrame(rows)


# ── Significance tests ────────────────────────────────────────────────────────

def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """P(a > b) - P(a < b). Ranges -1..1; |d| ≥ 0.474 is conventionally 'large'."""
    diff = a[:, None] - b[None, :]
    return float((np.sign(diff)).mean())


def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (step-down, monotone)."""
    m     = len(pvals)
    order = np.argsort(pvals)
    adj   = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i]  = min(1.0, running)
    return adj.tolist()


def _safe_test(fn, *samples) -> tuple[float, float]:
    """Rank tests raise when every value is identical (e.g. all at ceiling)."""
    try:
        res = fn(*samples)
        return float(res.statistic), float(res.pvalue)
    except ValueError:
        return float("nan"), 1.0


def significance_tests(per_run: pd.DataFrame,
                       level_order: list[str] | None = None) -> pd.DataFrame:
    """
    per_run needs columns model_id, task, vagueness_level, completeness_score.
    Returns one 'omnibus' row and one row per level pair for each (model, task).
    """
    rows = []
    for (model, task), sub in per_run.groupby(["model_id", "task"], sort=False):
        levels = [lv for lv in (level_order or sorted(sub["vagueness_level"].unique()))
                  if lv in set(sub["vagueness_level"])]
        samples = {lv: sub.loc[sub["vagueness_level"] == lv, "completeness_score"]
                         .dropna().to_numpy() for lv in levels}
        samples = {lv: s for lv, s in samples.items() if len(s)}
        if len(samples) < 2:
            continue

        h, p = _safe_test(stats.kruskal, *samples.values())
        rows.append({
            "model_id": model, "task": task, "comparison": "omnibus (Kruskal-Wallis)",
            "level_a": "", "level_b": "",
            "n_a": sum(len(s) for s in samples.values()), "n_b": np.nan,
            "statistic": h, "p_value": p, "p_holm": p, "cliffs_delta": np.nan,
        })

        pairs = list(itertools.combinations(samples, 2))
        pair_rows = []
        for a, b in pairs:
            u, p = _safe_test(
                lambda x, y: stats.mannwhitneyu(x, y, alternative="two-sided"),
                samples[a], samples[b],
            )
            pair_rows.append({
                "model_id": model, "task": task, "comparison": f"{a} vs {b}",
                "level_a": a, "level_b": b,
                "n_a": len(samples[a]), "n_b": len(samples[b]),
                "statistic": u, "p_value": p,
                "cliffs_delta": cliffs_delta(samples[a], samples[b]),
            })
        for r, adj in zip(pair_rows, holm([r["p_value"] for r in pair_rows])):
            r["p_holm"] = adj
        rows.extend(pair_rows)

    return pd.DataFrame(rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    from analysis.aggregate_results import build_per_run_summary, load_scored_outputs

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    records = load_scored_outputs()
    if not records:
        return
    sig = significance_tests(build_per_run_summary(records),
                             level_order=["baseline", "low", "medium", "high"])
    SIG_CSV.parent.mkdir(parents=True, exist_ok=True)
    sig.to_csv(SIG_CSV, index=False)
    log.info("Saved -> %s", SIG_CSV)
    print(sig.to_string(index=False))


if __name__ == "__main__":
    main()
