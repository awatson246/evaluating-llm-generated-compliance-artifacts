# Evaluating LLM-Generated Compliance Artifacts

The regulatory language used in the ESPR and GDPR is inherently vague; while humans may be able to use reasoning to interpret this language, it is not immediately clear that LLMs have this ability. This work explores how the vague language present in the GDPR and ESPR impacts the quality and consistency of LLM-produced compliance artifacts.

## Experiment Design

| Dimension | Values |
|---|---|
| **Tasks** | ESPR/DBP (AAS Material Composition submodel, IDTA 02035-6), GDPR/DPIA (Article 35(7)) |
| **Vagueness levels** | Baseline (direct quote from regulation), Low (task only), Medium (task + plain-language summary), High (task + regulatory text) |
| **Models** | GPT-4o, Claude Sonnet 4.6, Llama 3.1 8B, Ministral 8B, Qwen 2.5 7B |
| **Runs per condition** | 20 |
| **Total** | 2 tasks × 4 levels × 5 models × 20 runs = **800 runs** |
| **Generation** | temperature 0.7; output cap 32,000 tokens, lowered where a model cannot allow it (below) |

Each run produces a structured JSON artifact that is scored for:

- **Completeness**: the fraction of the schema's required fields that a single generated artifact actually includes.
- **Consistency**: how reliably repeated runs of the same prompt and model make the same decisions about which fields to include. Reported two ways:
  - `overall_consistency`: mean per-field inclusion rate across runs. A field omitted in every run scores 0, so this partly tracks completeness.
  - `overall_agreement`: mean per-field fraction of run pairs that make the same include/omit decision, `[C(k,2) + C(n-k,2)] / C(n,2)` for a field included in k of n runs. A field omitted in every run scores 1.

### Models

| Label | `model_id` | Provider | Served by | Output cap |
|---|---|---|---|---|
| GPT-4o | `gpt-4o` | OpenAI | `gpt-4o-2024-08-06` | 16,384 (model maximum) |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | Anthropic | `claude-sonnet-4-6` | 32,000 |
| Llama 3.1 8B | `meta-llama/Llama-3.1-8B-Instruct` | Hugging Face | nscale backend (pinned) | 32,000 |
| Ministral 8B | `ministral-8b-2512` | Mistral | `ministral-8b-2512` | 32,000 |
| Qwen 2.5 7B | `Qwen/Qwen2.5-7B-Instruct` | Hugging Face | HF auto-routing | 32k context minus prompt (≈14k on ESPR-high) |

Each raw output records the model that actually served it (`served_model`), the cap applied (`generation.max_tokens`) and a hash of the prompt (`prompt_sha256`).

### Data notes and limitations

- **Collection dates.** For GPT-4o, Claude Sonnet 4.6 and Qwen 2.5 7B, runs 1–3 (GDPR) and runs 1–5 (ESPR) were collected in May 2026 with a 6,000-token cap, before the provenance fields above existed. Only May runs that finished below that cap were kept (all 12 GDPR runs per model; 15 ESPR runs for GPT-4o and Qwen, 8 for Claude); the rest were regenerated in October 2026 with the 32k cap. All Llama 3.1 8B and Ministral 8B runs are from October.
- **Truncation at the output cap.** Kept and reported rather than re-run, because re-running reproduces them (or, for runaway generations, would bias the sample toward short outputs):

  | Condition | Truncated | Cause |
  |---|---|---|
  | Claude Sonnet 4.6, ESPR high | 20/20 | Reproduces the full AAS template; exceeds 32k |
  | GPT-4o, ESPR high | 19/20 | Model output maximum (16,384) |
  | Qwen 2.5 7B, ESPR high | 16/20 | 32k context window |
  | Llama 3.1 8B, ESPR high | 3/20 | Template reproduction / repetition |
  | Ministral 8B, ESPR low | 1/20 | Runaway generation |

- **ESPR ceiling.** Nearly all ESPR conditions score 1.00 completeness with no variance, including truncated runs, so the keyword scorer does not currently discriminate ESPR artifacts.
- **Excluded runs** (duplicates from concurrent batches, runs cut off by earlier 6k/10k caps, Llama runs on a different backend, superseded Mistral models) are preserved in git history under `src/outputs/raw/archived/` at commit `c90f942`.

## Repository Structure

```
src/
├── prompts/
│   ├── {gdpr,espr}_{baseline,low,medium,high}.txt   # Prompt per task × vagueness level
│   ├── product_data.md                              # ESPR product scenario ({{PRODUCT_DATA}})
│   ├── regulatory_text.md                           # ESPR regulatory text ({{REGULATORY_TEXT}})
│   ├── regulatory_text_annotations.md               # ESPR plain-language summary ({{REGULATORY_ANNOTATIONS}})
│   └── IDTA 02035-6_..._without_examplevalues.json  # AAS template ({{IDTA_TEMPLATE}})
├── schemas/
│   ├── dpia_schema.json               # Article 35(7) fields for GDPR scoring
│   └── aas_dpp_schema.json            # IDTA Material Composition submodel for ESPR scoring
├── models/                            # One wrapper per provider (OpenAI, Anthropic, Hugging Face, Mistral)
├── scoring/
│   ├── schema_scorer.py               # Field completeness scorer
│   └── consistency_scorer.py          # Cross-run consistency and agreement
├── analysis/
│   ├── aggregate_results.py           # Scores → summary CSVs (+ bootstrap CIs, significance tests)
│   ├── statistics.py                  # Bootstrap CIs + significance tests
│   ├── export_tables.py               # Summary CSVs → LaTeX tables
│   ├── plot_results.py                # Summary CSVs → figures
│   └── labels.py                      # Model and field display names shared by tables and figures
├── outputs/
│   ├── raw/                           # One JSON per run (800)
│   ├── scored/                        # One scored JSON per run (800)
│   ├── figures/                       # PDF + PNG figures
│   └── *.csv, latex_tables.tex        # Aggregates, significance tests, tables
├── run_experiment.py                  # Runs the experiment (async, resumable)
├── run_scoring.py                     # Scores raw outputs
├── archive_runs.py                    # Moves duplicate / cap-truncated runs out of outputs/raw
├── config.yaml.example                # Template — copy to config.yaml
└── requirements.txt
```

## Setup

```bash
pip install -r src/requirements.txt
cp src/config.yaml.example src/config.yaml
# Edit config.yaml — add your API keys (openai, anthropic, huggingface, mistral). This file is gitignored.
```

To test the setup on a single condition without spending much, run `python run_experiment.py --dry-run` from `src/` (configured under `dry_run:` in `config.yaml`).

## Running the Experiment

```bash
cd src
python run_experiment.py --plan    # list pending runs per model and task; no API calls
python run_experiment.py           # run everything pending
python run_experiment.py --task gdpr   # or one task
```

- **Resumable.** Runs are keyed by run number, and each result is saved as soon as it arrives, so an interrupted batch picks up where it stopped. `--runs N` overrides `num_runs`.
- **Out of credit.** A provider that runs out of credit is skipped for the rest of the batch; top up and re-run.
- **One batch at a time.** A lock file stops a second batch from starting and duplicating calls.
- **Retries.** Rate limits and transient server errors are retried with backoff; a call with no response after `call_timeout_seconds` (default 1800) is retried.
- **Streaming.** Claude and the Hugging Face models are streamed, since long non-streaming generations are refused or time out.

Raw outputs are saved to `outputs/raw/{model_id}__{task}__{level}__run{N}__{timestamp}.json`:

```json
{
  "model_id": "gpt-4o",
  "task": "gdpr",
  "vagueness_level": "high",
  "run_number": 1,
  "timestamp": "2026-10-05T...",
  "raw_response": "...",
  "usage": {"prompt_tokens": 412, "completion_tokens": 1823, "total_tokens": 2235},
  "latency_seconds": 8.4,
  "parsed_fields": {},
  "served_model": "gpt-4o-2024-08-06",
  "generation": {"temperature": 0.7, "max_tokens": 16384, "requested_max_tokens": 32000},
  "prompt_sha256": "..."
}
```

After a batch, `python archive_runs.py` previews duplicate run numbers and runs cut off at the configured cap (`--apply` moves them to `outputs/raw/archived/`; nothing is deleted). Runs truncated at a model's own lower limit are listed but kept.

## Scoring and Analysis

```bash
cd src
python run_scoring.py                      # or --task gdpr / --task espr; --stability-threshold 0.667
python analysis/aggregate_results.py
python analysis/export_tables.py
python analysis/plot_results.py
```

This produces:
1. `outputs/aggregate_summary.csv` — per (model, task, level): mean_completeness, std_completeness, group_completeness, overall_consistency, overall_agreement, n_runs, plus 95% bootstrap CIs (`completeness_ci_*`, `consistency_ci_*`, `agreement_ci_*`; 10,000 resamples of runs, seed 0; the agreement CI is bias-corrected because resampled duplicate runs always agree)
2. `outputs/field_stability.csv` — per (model, task, level, field): stability score + required flag
3. `outputs/significance_tests.csv` — per (model, task): Kruskal-Wallis across vagueness levels, then pairwise Mann-Whitney U with Holm correction and Cliff's delta
4. `outputs/latex_tables.tex` — per task: completeness, consistency and agreement (mean [95% CI]), required field inclusion rates, pairwise significance
5. `outputs/figures/` — per task (PDF + PNG): completeness, consistency and agreement bars with 95% CI error bars, field inclusion heatmap, completeness vs. consistency scatter

## Adding a New Model

1. Add an entry to `config.yaml` under `models:` (Hugging Face models can pin a backend with `hf_provider` and set `context_limit`).
2. If it's a new provider, subclass `BaseModel` in `models/` and register it in `models/__init__.py`.
3. Add its display name to `MODEL_LABELS` in `analysis/labels.py`.
