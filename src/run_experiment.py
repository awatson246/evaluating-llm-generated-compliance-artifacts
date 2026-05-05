"""
Main orchestrator for the LLM compliance artifact evaluation experiment.

Usage:
    cd research_pipeline
    python run_experiment.py               # follow config.yaml settings
    python run_experiment.py --dry-run     # override: single condition, no schema needed
    python run_experiment.py --config path/to/other_config.yaml
    python run_experiment.py --task espr   # run only ESPR/AAS across all levels
    python run_experiment.py --task gdpr   # run only GDPR/DPIA across all levels
    python run_experiment.py --task espr --task gdpr  # explicit multi-task override
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from models import build_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT        = Path(__file__).parent
PROMPTS_DIR = ROOT / "prompts"
OUTPUTS_RAW = ROOT / "outputs" / "raw"


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_prompt(task: str, vagueness_level: str) -> str:
    path = PROMPTS_DIR / f"{task}_{vagueness_level}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# ── Output ────────────────────────────────────────────────────────────────────

def save_raw(record: dict) -> None:
    OUTPUTS_RAW.mkdir(parents=True, exist_ok=True)
    safe_model = record["model_id"].replace("/", "_")
    ts         = record["timestamp"].replace(":", "-").replace("+", "")
    filename   = f"{safe_model}__{record['task']}__{record['vagueness_level']}__run{record['run_number']}__{ts}.json"
    out        = OUTPUTS_RAW / filename
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    log.info("Saved  %s", out.name)


# ── Experiment ────────────────────────────────────────────────────────────────

async def run_one(model, task: str, level: str, run_num: int, sem: asyncio.Semaphore) -> dict:
    prompt = load_prompt(task, level)
    async with sem:
        log.info("START  %-40s  task=%-5s  level=%-6s  run=%d",
                 model.model_id, task, level, run_num)
        resp = await model.generate(prompt)

    return {
        "model_id":        resp.model_id,
        "task":            task,
        "vagueness_level": level,
        "run_number":      run_num,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "raw_response":    resp.raw_text,
        "usage":           resp.usage,
        "latency_seconds": round(resp.latency_seconds, 3),
        "parsed_fields":   {},   # populated by scoring phase once schemas are finalised
    }


def build_conditions(config: dict, force_dry_run: bool, task_filter: list[str] | None = None) -> list[tuple[str, str, str, str, int]]:
    """Return list of (provider, model_id, task, vagueness_level, run_number)."""
    dry_cfg = config.get("dry_run", {})
    if force_dry_run or dry_cfg.get("enabled", False):
        log.info("DRY RUN — single condition only")
        provider, model_id = dry_cfg["model"].split("/", 1)
        return [(provider, model_id, dry_cfg["task"], dry_cfg["vagueness_level"], 1)]

    # CLI --task flag > config filter_tasks > all tasks in config
    tasks = task_filter or config.get("filter_tasks") or config["tasks"]
    unknown = set(tasks) - set(config["tasks"])
    if unknown:
        raise ValueError(f"Unknown task(s): {unknown}. Valid tasks: {config['tasks']}")
    log.info("Running tasks: %s", tasks)

    return [
        (entry["provider"], entry["model_id"], task, level, run)
        for entry in config["models"]
        for task  in tasks
        for level in config["vagueness_levels"]
        for run   in range(1, config["num_runs"] + 1)
    ]


async def run_experiment(config: dict, force_dry_run: bool = False, task_filter: list[str] | None = None) -> None:
    conditions = build_conditions(config, force_dry_run, task_filter)
    log.info("Conditions to run: %d", len(conditions))

    keys        = config["api_keys"]
    sem         = asyncio.Semaphore(config.get("max_concurrent", 5))
    model_cache: dict[tuple, object] = {}
    coros       = []

    for provider, model_id, task, level, run in conditions:
        key = (provider, model_id)
        if key not in model_cache:
            model_cache[key] = build_model(provider, model_id, api_key=keys[provider])
        coros.append(run_one(model_cache[key], task, level, run, sem))

    results = await asyncio.gather(*coros, return_exceptions=True)

    ok, err = 0, 0
    for result in results:
        if isinstance(result, Exception):
            log.error("Condition failed: %s", result)
            err += 1
        else:
            save_raw(result)
            ok += 1

    log.info("Finished — %d succeeded, %d failed", ok, err)
    if err:
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the LLM compliance artifact evaluation experiment."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Override config: run a single condition to verify setup."
    )
    parser.add_argument(
        "--config", default=str(ROOT / "config.yaml"),
        help="Path to config.yaml (default: src/config.yaml)"
    )
    parser.add_argument(
        "--task", dest="tasks", action="append", metavar="TASK",
        help="Run only this task (espr or gdpr). Repeat to include multiple. Overrides config."
    )
    args        = parser.parse_args()
    config      = load_config(Path(args.config))
    asyncio.run(run_experiment(config, force_dry_run=args.dry_run, task_filter=args.tasks))


if __name__ == "__main__":
    main()
