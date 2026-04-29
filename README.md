# Evaluating LLM-Generated Compliance Artifacts

The regulatory language used in the ESPR and GDPR is inherently vague; while humans may be able to use reasoning to interpret this language, it is not immediately clear that LLMs have this ability. This work explores how the vague language present in the GDPR and ESPR impacts the quality and consistency of LLM-produced compliance artifacts.

## Experiment Design

| Dimension | Values |
|---|---|
| **Tasks** | ESPR/DPP (AAS submodel), GDPR/DPIA (Article 35(7)) |
| **Vagueness levels** | Low (task only), Medium (task + plain-language summary), High (task + regulatory text) |
| **Models** | GPT-4o, Claude 3.5 Sonnet, Llama 3, Mistral, + 1 TBD |
| **Runs per condition** | 3 |
| **Total conditions** | 2 tasks × 3 levels × 5 models × 3 runs = **90 runs** |

Each run produces a structured JSON artifact that is scored for (1) field completeness against a schema and (2) cross-run consistency.

## Repository Structure

```
src/
├── prompts/
│   ├── gdpr_{low,medium,high}.txt     # GDPR/DPIA prompts (implemented)
│   └── espr_{low,medium,high}.txt     # ESPR/DPP prompts (scaffold — see co-author)
├── schemas/
│   ├── dpia_schema.json               # Article 35(7) fields for GDPR scoring
│   └── aas_dpp_schema.json            # AAS submodel fields for ESPR scoring (scaffold)
├── models/
│   ├── base_model.py                  # Abstract base class + ModelResponse dataclass
│   ├── openai_model.py
│   ├── anthropic_model.py
│   └── huggingface_model.py
├── scoring/
│   ├── schema_scorer.py               # Field completeness scorer (scaffold)
│   └── consistency_scorer.py          # Cross-run variance scorer (scaffold)
├── outputs/
│   ├── raw/                           # One JSON per run (gitignored contents)
│   └── scored/                        # Scored results per condition (gitignored contents)
├── analysis/
│   ├── aggregate_results.py           # Compile scores → summary CSV
│   └── export_tables.py               # Summary CSV → LaTeX tables
├── run_experiment.py                  # Main orchestrator (async)
├── config.yaml                        # API keys + run settings (gitignored)
├── config.yaml.example                # Template — copy to config.yaml
└── requirements.txt
```

## Setup

### 1. Install dependencies

```bash
pip install -r research_pipeline/requirements.txt
```

### 2. Configure API keys

```bash
cp research_pipeline/config.yaml.example research_pipeline/config.yaml
# Edit config.yaml — add your API keys. This file is gitignored.
```

### 3. (Optional) Test with dry run

The `dry_run` flag runs a single condition (one model, one task, one vagueness level, one run) to verify your setup without burning credits.

```bash
# Enable in config.yaml:
#   dry_run:
#     enabled: true

cd research_pipeline
python run_experiment.py

# Or override via CLI flag:
python run_experiment.py --dry-run
```

## Running the Full Experiment

```bash
cd research_pipeline
python run_experiment.py
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

> **Status**: Scoring modules are scaffolded. Finalize `dpia_schema.json` and `aas_dpp_schema.json` with your co-author before implementing `scoring/schema_scorer.py` and `scoring/consistency_scorer.py`.

Once schemas are finalized:
1. `schema_scorer.py` takes a parsed artifact + schema → per-field `present/absent` + overall completeness score (0–1)
2. `consistency_scorer.py` takes 3 runs of the same condition → field-level stability scores

## Analysis and Export

After scoring:

```bash
cd research_pipeline
python analysis/aggregate_results.py   # → outputs/aggregate_summary.csv
python analysis/export_tables.py       # → outputs/latex_tables.tex
```

The LaTeX tables are formatted for an AAAI-style paper: rows = vagueness levels, columns = models, cells = mean completeness or consistency score.

## Adding a New Model

1. Add an entry to `config.yaml` under `models:`
2. If it's a new provider, subclass `BaseModel` in `models/` and register it in `models/__init__.py`

## Notes

- `config.yaml` is gitignored. Never commit API keys.
- ESPR prompt files and `aas_dpp_schema.json` are scaffolds pending co-author input.
- `outputs/raw/` and `outputs/scored/` contents are gitignored; the directories are tracked via `.gitkeep`.
