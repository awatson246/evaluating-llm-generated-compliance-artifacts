"""
Move raw outputs that should not be pooled out of outputs/raw/ (nothing is deleted).

  duplicates  More than one file for the same (model, task, level, run number),
              e.g. from two batches running at once. The earliest file is kept.
  truncated   Output stopped at the configured max_tokens cap, so the artifact
              is cut off and later fields would be scored as missing.

Runs truncated at a lower model/provider limit (e.g. GPT-4o's 16384 output
maximum) are kept and listed instead: re-running would only reproduce them.

Matching files in outputs/scored/ are moved alongside so aggregation stops
counting them. Re-running run_experiment.py then regenerates the freed run
numbers under the current settings.

Usage:
    cd src
    python archive_runs.py                 # preview only
    python archive_runs.py --apply         # move files
    python archive_runs.py --cap-slack 10  # tokens below the cap that count as hitting it
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT        = Path(__file__).parent
OUTPUTS_RAW = ROOT / "outputs" / "raw"
OUTPUTS_SCO = ROOT / "outputs" / "scored"
ARCHIVE     = OUTPUTS_RAW / "archived"

# Runs saved before generation settings were recorded used this cap.
LEGACY_MAX_TOKENS = 6000

_RUN_KEY = re.compile(r"^(?P<key>.+__run\d+)__(?P<ts>.+)\.json$")


def output_tokens(rec: dict) -> int:
    u = rec.get("usage") or {}
    return int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0)


def find_archivable(cap_slack: int) -> tuple[dict[Path, str], dict[str, int]]:
    """
    Return ({raw_path: reason} for files to move,
            {condition: count} of runs truncated at a model's hard output limit, kept).
    """
    reasons: dict[Path, str] = {}
    hard_limited: dict[str, int] = defaultdict(int)
    by_key: dict[str, list[tuple[str, Path]]] = defaultdict(list)

    for p in OUTPUTS_RAW.glob("*.json"):
        m = _RUN_KEY.match(p.name)
        if not m:
            continue
        by_key[m["key"]].append((m["ts"], p))

        rec = json.loads(p.read_text(encoding="utf-8"))
        gen = rec.get("generation") or {}
        cap = gen.get("max_tokens", LEGACY_MAX_TOKENS)
        if output_tokens(rec) >= cap - cap_slack:
            # Below the configured cap means the model/provider maximum was hit
            # (e.g. GPT-4o's 16384). Re-running reproduces it, so keep the run
            # and report the truncation as a model limitation instead.
            if cap < gen.get("requested_max_tokens", cap):
                hard_limited[p.name.split("__run")[0]] += 1
            else:
                reasons[p] = f"truncated_{cap}"

    for files in by_key.values():
        for _, p in sorted(files)[1:]:   # keep the earliest timestamp
            reasons[p] = "duplicates"     # takes precedence over truncation
    return reasons, hard_limited


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="Move files (default: preview).")
    parser.add_argument("--cap-slack", type=int, default=10,
                        help="Output within this many tokens of max_tokens counts as truncated.")
    args = parser.parse_args()

    reasons, hard_limited = find_archivable(args.cap_slack)
    summary: dict[tuple[str, str], int] = defaultdict(int)
    for p, why in reasons.items():
        summary[(why, p.name.split("__run")[0])] += 1

    print(f"{'Reason':<16} {'Condition':<60} {'Files':>5}")
    for (why, cond), n in sorted(summary.items()):
        print(f"{why:<16} {cond:<60} {n:>5}")
    print(f"\n{len(reasons)} file(s) {'moved' if args.apply else 'would be moved'} "
          f"to {ARCHIVE.relative_to(ROOT)}/<reason>/")
    if hard_limited:
        print("\nKept, truncated at the model's own output limit (report as a limitation):")
        for cond, n in sorted(hard_limited.items()):
            print(f"  {cond:<60} {n:>5}")

    if not args.apply:
        return
    for p, why in reasons.items():
        for src, sub in ((p, "raw"), (OUTPUTS_SCO / p.name, "scored")):
            if src.exists():
                dest = ARCHIVE / why / sub / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dest)


if __name__ == "__main__":
    main()
