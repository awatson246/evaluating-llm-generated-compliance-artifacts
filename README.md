# Evaluating LLM-Generated Compliance Artifacts

The regulatory language used in the ESPR and GDPR is inherently vague; while humans may be able to use reasoning to interpret this language, it is not immediately clear that LLMs have this ability. This work explores how the vague language present in the GDPR and ESPR impacts the quality and consistency of LLM-produced compliance artifacts.

## Experiment Design

| Dimension | Values |
|---|---|
| **Tasks** | ESPR/DPP (AAS submodel), GDPR/DPIA (Article 35(7)) |
| **Vagueness levels** | Baseline (direct quote from regulation), Low (task only), Medium (task + plain-language summary), High (task + regulatory text) |
| **Models** | GPT-4o, Claude Sonnet 4.6, Llama 3.1, Mistral, Qwen-2.5 |
| **Runs per condition** | 20 (set via `num_runs` or `--runs`) |
| **Total conditions** | 2 tasks × 4 levels × 5 models × 20 runs = **800 runs** |

Each run produces a structured JSON artifact that is scored for:

- **Completeness**: the fraction of the schema's required fields that a single generated artifact actually includes.
- **Consistency**: how reliably repeated runs of the same prompt and model make the same decisions about which fields to include. Reported two ways:
  - `overall_consistency`: mean per-field inclusion rate across runs. A field omitted in every run scores 0, so this partly tracks completeness.
  - `overall_agreement`: mean per-field fraction of run pairs that make the same include/omit decision, `[C(k,2) + C(n-k,2)] / C(n,2)` for a field included in k of n runs. A field omitted in every run scores 1.

## Repository Structure

```
src/
├── prompts/
│   ├── gdpr_{low,medium,high}.txt     # GDPR/DPIA prompts (implemented)
│   └── espr_{low,medium,high}.txt     # ESPR/DPP prompts (scaffold)
├── schemas/
│   ├── dpia_schema.json               # Article 35(7) fields for GDPR scoring
│   └── aas_dpp_schema.json            # AAS submodel fields for ESPR scoring (scaffold)
├── models/
│   ├── base_model.py                  # Abstract base class + ModelResponse dataclass
│   ├── openai_model.py
│   ├── anthropic_model.py
│   └── huggingface_model.py
├── scoring/
│   ├── schema_scorer.py               # Field completeness scorer
│   └── consistency_scorer.py          # Cross-run variance scorer
├── outputs/
│   ├── raw/                           # One JSON per run (gitignored contents)
│   └── scored/                        # Scored results per condition (gitignored contents)
├── analysis/
│   ├── aggregate_results.py           # Compile scores → summary CSV (+ bootstrap CIs)
│   ├── statistics.py                  # Bootstrap CIs + significance tests
│   └── export_tables.py               # Summary CSV → LaTeX tables
├── run_experiment.py                  # Main orchestrator (async)
├── config.yaml                        # API keys + run settings (gitignored)
├── config.yaml.example                # Template — copy to config.yaml
└── requirements.txt
```

## Setup

### 1. Install dependencies

```bash
pip install -r src/requirements.txt
```

### 2. Configure API keys

```bash
cp src/config.yaml.example src/config.yaml
# Edit config.yaml — add your API keys. This file is gitignored.
```

### 3. (Optional) Test with dry run

The `dry_run` flag runs a single condition (one model, one task, one vagueness level, one run) to verify your setup without burning credits.

```bash
# Enable in config.yaml:
#   dry_run:
#     enabled: true

cd src
python run_experiment.py

# Or override via CLI flag:
python run_experiment.py --dry-run
```

## Running Just One Regulation
You can use CLi flags  to run just ESPR tasks:
```bash
cd src
python run_experiment.py --task espr
```
Or only GDPR tasks:
```bash
cd src
python run_experiment.py --task gdpr
```

## Adding More Runs

Runs are keyed by run number, so raising the run count only generates the missing ones; existing outputs are kept:
```bash
cd src
python run_experiment.py --runs 20
```
Each raw output records its `generation` settings (temperature, max_tokens) and a `prompt_sha256`, so you can check that runs collected in different batches are poolable.

## Running the Full Experiment

```bash
cd src
python run_experiment.py
```
or

```bash
cd src
python run_experiment.py --task espr --task gdpr
```

Raw outputs are saved to `outputs/raw/` as JSON files named:
`{model_id}_{task}_{vagueness_level}_run{N}_{timestamp}.json`

Each file contains:
```json
{
  "model_id": "gpt-4o",
  "task": "gdpr",
  "vagueness_level": "high",
  "run_number": 1,
  "timestamp": "2026-04-29T...",
  "raw_response": "...",
  "usage": {"prompt_tokens": 412, "completion_tokens": 1823, "total_tokens": 2235},
  "latency_seconds": 8.4,
  "parsed_fields": {}
}
```

## Scoring Pipeline

To score all tasks:
```bash
cd src
python run_scoring.py
```

or

To score just one task:
```bash
cd src
python run_scoring.py --task gdpr   # gdpr only
```

or

To specify a stability threshold:
```bash
cd src
python run_scoring.py --stability-threshold 0.667
```

## Analysis and Export

After scoring:

```bash
cd src
python analysis/aggregate_results.py
python analysis/export_tables.py
python analysis/plot_results.py
```
This returns: 
1. outputs/aggregate_summary.csv — per-(model, task, level): mean_completeness, std_completeness, group_completeness, overall_consistency, overall_agreement, n_runs, plus 95% bootstrap CIs (`completeness_ci_*`, `consistency_ci_*`, `agreement_ci_*`; 10,000 resamples of runs, seed 0; the agreement CI is bias-corrected because resampled duplicate runs always agree)
2. outputs/field_stability.csv — per-(model, task, level, field): stability score + required flag
3. outputs/significance_tests.csv — per-(model, task): Kruskal-Wallis across vagueness levels, then pairwise Mann-Whitney U with Holm correction and Cliff's delta
4. outputs/latex_tables.tex — 4 tables per task, drop-in ready:
  - Completeness (mean [95% CI], includes baseline row)
  - Consistency (same layout)
  - Agreement (same layout)
  - Required field inclusion rates
  - Pairwise vagueness-level significance
5. outputs/figures/ — 5 figures per task (PDF + PNG):
  - completeness_<task> — grouped bars by vagueness level, 95% CI error bars
  - consistency_<task> — same for consistency
  - agreement_<task> — same for agreement
  - field_heatmap_<task> — heatmap of field inclusion, sorted with most-excluded fields at top
  - completeness_vs_consistency_<task> — scatter with model shapes and vagueness colours

## Adding a New Model

1. Add an entry to `config.yaml` under `models:`
2. If it's a new provider, subclass `BaseModel` in `models/` and register it in `models/__init__.py`

## Notes

- `config.yaml` is gitignored. Never commit API keys.
- ESPR prompt files and `aas_dpp_schema.json` are scaffolds pending co-author input.
- `outputs/raw/` and `outputs/scored/` contents are gitignored; the directories are tracked via `.gitkeep`.
