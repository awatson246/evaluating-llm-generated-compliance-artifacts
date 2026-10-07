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
    python run_experiment.py --runs 20     # override num_runs (existing runs are skipped)
    python run_experiment.py --runs 20 --plan   # show what would run, no API calls
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
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
    prompt_path = PROMPTS_DIR / f"{task}_{vagueness_level}.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8")

    product_data = (
        PROMPTS_DIR / "product_data.md"
    ).read_text(encoding="utf-8")

    regulatory_text = (
        PROMPTS_DIR / "regulatory_text.md"
    ).read_text(encoding="utf-8")

    regulatory_annotations = (
        PROMPTS_DIR / "regulatory_text_annotations.md"
    ).read_text(encoding="utf-8")

    idta_template = (
        PROMPTS_DIR / "IDTA 02035-6_DBP-Part-6_MaterialComposition_without_examplevalues.json"
    ).read_text(encoding="utf-8")

    prompt_text = prompt_text.replace(
        "{{PRODUCT_DATA}}",
        product_data
    )

    prompt_text = prompt_text.replace(
        "{{REGULATORY_TEXT}}",
        regulatory_text
    )

    prompt_text = prompt_text.replace(
        "{{REGULATORY_ANNOTATIONS}}",
        regulatory_annotations
    )

    prompt_text = prompt_text.replace(
        "{{IDTA_TEMPLATE}}",
        idta_template
    )

    return prompt_text


# ── Output ────────────────────────────────────────────────────────────────────

def _safe_model(model_id: str) -> str:
    return model_id.replace("/", "_")


def already_done(model_id: str, task: str, level: str, run_num: int) -> bool:
    """Return True if a raw output file already exists for this condition."""
    pattern = f"{_safe_model(model_id)}__{task}__{level}__run{run_num}__*.json"
    return any(OUTPUTS_RAW.glob(pattern))


def save_raw(record: dict) -> None:
    OUTPUTS_RAW.mkdir(parents=True, exist_ok=True)
    ts       = record["timestamp"].replace(":", "-").replace("+", "")
    filename = f"{_safe_model(record['model_id'])}__{record['task']}__{record['vagueness_level']}__run{record['run_number']}__{ts}.json"
    out      = OUTPUTS_RAW / filename
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    log.info("Saved  %s", out.name)


# ── Experiment ────────────────────────────────────────────────────────────────

# Transient errors worth retrying with backoff: rate limits and provider outages.
_RATE_LIMIT_SIGNALS = ("429", "rate_limit", "rate limit", "ratelimit", "too many requests",
                       "500", "502", "503", "504", "internal server error", "service unavailable",
                       "bad gateway", "overloaded")

# Out-of-credit errors. Checked before rate limits because OpenAI reports
# insufficient_quota as a 429, and retrying those only burns time.
_QUOTA_SIGNALS = (
    "insufficient_quota", "exceeded your current quota", "credit balance is too low",
    "billing", "payment required", "402", "monthly included credits", "quota exceeded",
)


class QuotaExhausted(RuntimeError):
    """A provider has run out of credit; its remaining calls are skipped."""


def _is_quota(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _QUOTA_SIGNALS)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)


async def run_one(
    model,
    provider: str,
    task: str,
    level: str,
    run_num: int,
    sem: asyncio.Semaphore,
    exhausted: set[str],
    max_retries: int = 3,
    base_delay: float = 60.0,
    call_timeout: float = 1800.0,
) -> dict:
    prompt     = load_prompt(task, level)
    max_tokens = model.effective_max_tokens(prompt)
    delay      = base_delay
    for attempt in range(max_retries + 1):
        async with sem:
            if provider in exhausted:
                raise QuotaExhausted(f"{provider} out of credit — skipped")
            log.info("START  %-40s  task=%-5s  level=%-6s  run=%d  (attempt %d)",
                     model.model_id, task, level, run_num, attempt + 1)
            try:
                # A stalled connection otherwise holds its semaphore slot forever;
                # five of them deadlock the whole batch. The limit sits well above
                # the slowest genuine generation so long outputs are not dropped.
                resp = await asyncio.wait_for(model.generate(prompt, max_tokens=max_tokens),
                                              timeout=call_timeout)
            except asyncio.TimeoutError:
                if attempt >= max_retries:
                    raise RuntimeError(f"no response after {call_timeout:.0f}s "
                                       f"({max_retries + 1} attempts)")
                log.warning("TIMEOUT %s task=%s level=%s run=%d after %.0fs — retrying",
                            model.model_id, task, level, run_num, call_timeout)
                continue
            except Exception as exc:
                if _is_quota(exc):
                    if provider not in exhausted:
                        log.error("QUOTA  %s is out of credit — skipping its remaining calls. "
                                  "Top up and re-run; completed runs are kept. (%s)", provider, exc)
                    exhausted.add(provider)
                    raise QuotaExhausted(f"{provider} out of credit") from exc
                if attempt >= max_retries or not _is_rate_limit(exc):
                    raise
                log.warning("Rate-limited (%s/%s) — sleeping %.0fs before retry",
                            attempt + 1, max_retries, delay)
            else:
                break
        # semaphore is released before sleeping so other calls can proceed
        await asyncio.sleep(delay)
        delay *= 2

    if not (resp.raw_text or "").strip():
        # Don't save: an empty file would mark this run done and block a retry.
        raise RuntimeError(f"{model.model_id} returned an empty response")

    return {
        "model_id":        resp.model_id,
        "task":            task,
        "vagueness_level": level,
        "run_number":      run_num,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "raw_response":    resp.raw_text,
        "usage":           resp.usage,
        "latency_seconds": round(resp.latency_seconds, 3),
        "parsed_fields":   {},
        "served_model":    resp.served_model,
        # Provenance: lets runs collected in different batches be checked for
        # identical generation settings and prompt text before being pooled.
        "generation": {
            "temperature":          model.temperature,
            "max_tokens":           max_tokens,        # cap actually applied
            "requested_max_tokens": model.max_tokens,  # cap from config
        },
        "prompt_sha256":   hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }


def build_conditions(config: dict, force_dry_run: bool, task_filter: list[str] | None = None,
                     num_runs: int | None = None) -> list[tuple[str, str, str, str, int]]:
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
        for run   in range(1, (num_runs or config["num_runs"]) + 1)
    ]


def print_plan(pending: list[tuple], skipped: int) -> None:
    """Summarise outstanding calls per (model, task) without calling any API."""
    counts: dict[tuple[str, str], int] = {}
    for _, model_id, task, _, _ in pending:
        counts[(model_id, task)] = counts.get((model_id, task), 0) + 1
    print(f"\n{'Model':<42} {'Task':<6} {'Pending':>7}")
    for (model_id, task), n in sorted(counts.items()):
        print(f"{model_id:<42} {task:<6} {n:>7}")
    print(f"\n{len(pending)} pending, {skipped} already done\n")


async def run_experiment(config: dict, force_dry_run: bool = False, task_filter: list[str] | None = None,
                         num_runs: int | None = None, plan_only: bool = False) -> None:
    conditions = build_conditions(config, force_dry_run, task_filter, num_runs)
    pending    = [c for c in conditions if not already_done(c[1], c[2], c[3], c[4])]
    skipped    = len(conditions) - len(pending)
    log.info("Conditions: %d total, %d already in outputs/raw, %d to run",
             len(conditions), skipped, len(pending))
    if plan_only:
        print_plan(pending, skipped)
        return

    retry_cfg   = config.get("retry", {})
    max_retries = retry_cfg.get("max_retries", 3)
    base_delay  = retry_cfg.get("base_delay_seconds", 60.0)
    call_timeout = config.get("call_timeout_seconds", 1800)

    gen_cfg     = config.get("generation", {})
    keys        = config["api_keys"]
    sem         = asyncio.Semaphore(config.get("max_concurrent", 5))
    exhausted: set[str] = set()
    model_cache: dict[tuple, object] = {}
    counts      = {"ok": 0, "err": 0, "quota": 0}

    async def run_and_save(provider, model_id, task, level, run) -> None:
        # Save each result as soon as it arrives so an interrupted or partly
        # failed batch keeps everything that finished; re-running skips it.
        async with sem:
            # Re-check just before calling: another batch may have filled it.
            if already_done(model_id, task, level, run):
                return
        try:
            record = await run_one(model_cache[(provider, model_id)], provider, task, level,
                                   run, sem, exhausted, max_retries, base_delay, call_timeout)
        except QuotaExhausted:
            counts["quota"] += 1
        except Exception as exc:
            log.error("FAIL   %-40s  task=%-5s  level=%-6s  run=%d  %s",
                      model_id, task, level, run, exc)
            counts["err"] += 1
        else:
            save_raw(record)
            counts["ok"] += 1

    # Per-model options from config (e.g. hf_provider, context_limit) beyond provider/model_id
    model_opts = {
        (m["provider"], m["model_id"]): {k: v for k, v in m.items() if k not in ("provider", "model_id")}
        for m in config["models"]
    }
    for provider, model_id, *_ in pending:
        key = (provider, model_id)
        if key not in model_cache:
            model_cache[key] = build_model(provider, model_id, api_key=keys[provider],
                                           **{**gen_cfg, **model_opts.get(key, {})})

    await asyncio.gather(*(run_and_save(*c) for c in pending))

    log.info("Finished — %d succeeded, %d failed, %d skipped for lack of credit",
             counts["ok"], counts["err"], counts["quota"])
    if exhausted:
        log.warning("Out of credit: %s. Top up, then re-run the same command to resume.",
                    ", ".join(sorted(exhausted)))
    if counts["err"] or counts["quota"]:
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

LOCK_FILE = OUTPUTS_RAW / ".run_experiment.lock"


def acquire_lock() -> bool:
    """
    Refuse to start while another batch is running: both would plan the same
    run numbers and pay for every call twice. Removed on exit; if a crash
    leaves it behind, delete the file by hand.
    """
    OUTPUTS_RAW.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        log.error("Another run appears to be in progress (%s exists: %s). "
                  "If it is not, delete that file and retry.",
                  LOCK_FILE, LOCK_FILE.read_text(encoding="utf-8", errors="replace").strip())
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"pid {os.getpid()} started {datetime.now().isoformat(timespec='seconds')}")
    return True


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
    parser.add_argument(
        "--runs", type=int, metavar="N",
        help="Number of runs per condition. Overrides num_runs in config. "
             "Runs already in outputs/raw are skipped, so raising N only adds new runs."
    )
    parser.add_argument(
        "--plan", action="store_true",
        help="List pending runs per model and task, then exit without calling any API."
    )
    args        = parser.parse_args()
    config      = load_config(Path(args.config))
    if args.plan:
        asyncio.run(run_experiment(config, force_dry_run=args.dry_run, task_filter=args.tasks,
                                   num_runs=args.runs, plan_only=True))
        return
    if not acquire_lock():
        sys.exit(2)
    try:
        asyncio.run(run_experiment(config, force_dry_run=args.dry_run, task_filter=args.tasks,
                                   num_runs=args.runs))
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
