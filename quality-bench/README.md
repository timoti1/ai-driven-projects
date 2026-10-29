# quality-bench

LLM quality benchmark: runs a fixed, seeded sample of well-known benchmarks
(MMLU, GSM8K, HellaSwag, ARC, MATH, Winogrande, BBH, HumanEval, Terminal,
TerminalHard) against a local model served by LM Studio, in fresh Docker
containers, and scores the results deterministically.

## Layout

| Path | Contents |
|------|----------|
| `questions/` | blind questions per benchmark (no answers) — inputs to the containers |
| `truth/` | ground-truth answers per benchmark — host-only, never mounted into containers |
| `terminal_sandboxes/` | clean terminal task sandboxes (50 tasks) |
| `terminal_sandboxes_hard/` | clean hard terminal task sandboxes (50 tasks) |
| `runs/` | per-run artifacts: `runs/<MODEL>_<RUN_ID>/` (answers, solutions, terminal outputs, event logs) |
| `results/` | `results_<RUN_NAME>.json` — per-benchmark scores + time |
| `meta/` | `meta_<RUN_NAME>.json` — run metadata (notes, context size, auto-resolved model file, compactions — recorded automatically by run.sh) |
| `bin/` | container helper scripts (`_show_batch.py`, `_append_batch.py`, `_time.py`, `_progress.py`) |
| `.stage/` | transient per-run staging (deleted on full success) |
| `.benchenv/` | Python venv for the host-side scripts |

## Files

- `prepare.py`, `download.py` — Phase 1: build the fixed question/truth samples (seed=1234)
- `prepare_terminal.py`, `prepare_terminal_hard.py` — Phase 1: generate terminal task sandboxes
- `run.sh` — Phase 2: launch a fresh Docker container per benchmark against LM Studio
- `score.py` — Phase 3: score a run against the truth, write `results/`
- `verify.py` — host-side quick check of answer completeness
- `compare.py`, `report.py` — aggregate all runs into comparison tables
- `clean.py` — wipe runs (archive or purge) to start the table from scratch
- `Dockerfile`, `INSTRUCTIONS.md` — container image + the model's task brief
- `SCORING.md` — operator runbook (phases, steps, scoring rules)

## Quick start

```bash
# 1. build the fixed samples (once)
./.benchenv/bin/python prepare.py
./.benchenv/bin/python prepare_terminal.py
./.benchenv/bin/python prepare_terminal_hard.py

# 2. run a model (default: LM Studio at 192.168.1.104:8080)
./run.sh <MODEL> [RUN_ID] [NOTE] [SEED]
# optional SEED (or BENCH_SEED env) pins generation sampling for reproducible runs

# remote / hosted models (OpenRouter, OpenAI, any OpenAI-compatible endpoint):
export OPENROUTER_API_KEY=sk-or-...
BENCH_HOST=openrouter.ai BENCH_PORT=443 BENCH_SCHEME=https BENCH_PATH_PREFIX=/api \
  BENCH_API_KEY_ENV=OPENROUTER_API_KEY BENCH_API=openai-completions \
  ./run.sh nvidia/nemotron-3.5-super-vl:free [RUN_ID] [NOTE] [SEED]

# env var reference:
#   BENCH_HOST / BENCH_PORT / BENCH_SCHEME   -> endpoint (default: 192.168.1.104:8080 http)
#   BENCH_PATH_PREFIX                       -> URL prefix before /v1/... (OpenRouter: /api)
#   BENCH_API_KEY_ENV                       -> env var name holding the API key
#   BENCH_API_KEY                           -> literal key fallback (less secure)
#   BENCH_API                               -> pi agent api value (default: openai-completions)
#   BENCH_CTX                               -> context window override (auto-detected for llama-swap)
#   BENCH_SKIP_FILE_LOOKUP=1                -> skip GGUF file resolution (needed for remote endpoints)
#   LMSTUDIO_HOST / LMSTUDIO_PORT / LMSTUDIO_KEY   -> legacy aliases for BENCH_HOST/PORT/KEY

# Loop detection (prevents infinite loops on a stubborn model):
#   bin/_progress.py watches the pi event stream inside each container and kills
#   the container if the same assistant text or the same tool command repeats
#   10 times in a row (LOOP_LIMIT = 10). The run moves to the next bench and the
#   killed one is marked FAILED. Check pi_stream_<bench>.jsonl to debug.

# 3. score + compare
./.benchenv/bin/python score.py <RUN_NAME>
./.benchenv/bin/python compare.py
python3 report.py
```

See `SCORING.md` for the full operator workflow and `INSTRUCTIONS.md` for what
the model is told inside the container.
