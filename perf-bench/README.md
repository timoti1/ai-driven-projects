# perf-bench

Portable, dependency-free (stdlib python3, bash/powershell only) performance harness for
any OpenAI-compatible inference server: llama.cpp/llama-swap, vLLM, LM Studio, Ollama's
`/v1`, hosted endpoints. Vendor-agnostic: AMD, NVIDIA, Intel, CPU - the harness only
talks HTTP; local GPU counters are probed best-effort via `nvidia-smi` or `rocm-smi`
when present. No hostnames, IPs, models, or paths are hardcoded in the code.

## Quick start

```bash
./install.sh                       # optional: installs `pb` launcher + starter perf-bench.json
python3 bench.py --target local --model PUT-MODEL --tests health,prefill,decode
python3 summarize.py               # markdown pivot of results/runs.csv
```

Remote / hosted models (OpenRouter, OpenAI, and any Pi-agent-accessible OpenAI-compatible endpoint):
```bash
export OPENROUTER_API_KEY=sk-or-...
python3 bench.py --target openrouter --model openrouter/auto --tests health,prefill,decode

# via plain flags (OpenRouter needs path_prefix=/api):
python3 bench.py --scheme https --host openrouter.ai --port 443 --path-prefix /api \
  --model openrouter/auto --api-key-env OPENROUTER_API_KEY --tests health,decode

# any endpoint Pi agent proxies (e.g. its local llama.cpp router):
python3 bench.py --host <router-host> --port <port> --model <model-id> --api-key-env <KEY_VAR>
```

Windows: `powershell -File install.ps1` then `pb --config perf-bench.json`.

## Resolution order

CLI flags > config file > localhost defaults.
Config file search: `--config` path, `$PERF_BENCH_CONFIG`, `./perf-bench.json`,
`./perf-bench.yaml` (needs PyYAML), `~/.config/perf-bench/config.json|yaml`,
`%APPDATA%\perf-bench\config.json`. Presets: `presets/targets.json` (example provided).
**If neither args nor a config define anything, the tool prints usage and explains that
it is unclear what to benchmark (exit code 2)** instead of guessing.

## What it measures

| test suite | metric | how |
|---|---|---|
| `tests/health.json` | health_ok | `/health` + `/v1/models` reachability, latency |
| `tests/prefill.json` | prefill_tps | unique prompts at several sizes (no cache reuse) |
| `tests/decode.json` | decode_tps, first_token_s | single streaming request per context depth |
| `tests/kv-cache.json` | cache_hit_tps, speedup_vs_cold | cold fill of a large shared prefix, then N queries hitting it |
| `tests/spec-decode.json` | prefill_tps, decode_tps, mtp_acc | long prompt, long generation, draft acceptance tracked - the suite to use when speculative decoding is on |
| `tests/full.json` | all of the above | combined smoke suite |
| `--llama-bench EXE --gguf M.gguf` | pp/tg from the binary | parses llama.cpp `llama-bench` output into the same CSV |

## Trustworthy numbers

The measurement model, and why each rule is there. Every one of these was
learned from a number that looked fine and was wrong.

- **Server counters beat wall clock.** llama.cpp reports `timings`
  (`prompt_per_second`, `predicted_per_second`, `cache_n`, `draft_n`,
  `draft_n_accepted`). Those exclude HTTP and queue time, so they are used when
  present; wall-clock derivation is a fallback for servers that do not expose
  them (`detail` says `src=server` or `src=derived`).
- **The cache-busting nonce goes at the front of the prompt.** The prompt cache
  is matched from token 0, so a trailing nonce leaves the entire prefix cached
  and "prefill" becomes a cache hit - typically 5-15x too fast, and not
  reproducible. `lib/prompt.py` puts the nonce first, and `spec-decode` asserts
  `cache_n` on every cold rep: a rep with >20% cache hits flags the run
  (`cache_bust=False`) instead of being averaged into the median.
- **Prefill and decode need opposite cache states.** Prefill must be cold (front
  nonce, generation suppressed). Decode must be warm: one warm-up call on the
  byte-identical prompt, then the measured reps. Measuring decode on a fresh
  random prompt every rep folds a full prefill into the number.
- **Repetitions are reported with spread, not as a single value.** Median plus
  min/max; `summarize.py` marks cells with >10% spread `⚠`. A single call per
  configuration is not a measurement - on this class of hardware the same config
  varies 5-30% run to run depending on context length and thermal state.
- **Decode tok/s is meaningless without acceptance rate.** A drafter that guesses
  more often can look "better" while being slower. `mtp_acc` (accepted draft
  tokens / drafted tokens) and mean draft length are recorded next to decode
  speed, and the two together are what decide a drafter configuration.
- **Fixed seed, temperature 0, byte-identical prompt.** Prompts are grown to a
  target token count and calibrated against `/tokenize` when a llama.cpp server
  is reachable, so runs are comparable across engines and across days.
- **Never measure a model that is serving you.** Agent traffic on the same engine
  contaminates the run (and evicting it kills the session). `ab.py` binds arms to
  a dedicated port; `bench.py --tests sweep`-style runs through a router should
  exclude the model answering the harness.

## Comparing configurations: `ab.py`

```bash
python3 ab.py ab    --spec ab.example.json --reps 3 --rounds 2 --gen 1024 --prompt-tokens 8000
python3 ab.py probe --spec ab.example.json --reps 3 --gen 1024
```

`ab` runs arms **alternately** across rounds (round 0: A,B; round 1: B,A; ...).
Thermal state, clock drift and background load then hit both arms equally, so a
difference that survives alternation is a configuration effect. Sequential A-then-B
measurement is how most published comparisons get their fake deltas. Each arm is a
shell template (`{port}`, `{name}`, `{log}`, `{model}`, `{host}` are substituted;
curl's `%{http_code}` is left alone), so any launch path works: local process, ssh,
container, cluster submit. Site-specific specs stay out of the repo (`ab.<site>.json`
is gitignored; `ab.example.json` is the template).

`probe` answers an interference question with data instead of intuition: it measures
the target with the competing workload idle, then saturated, and reports the delta
with a verdict. Whether an expert-streaming model on one GPU perturbs a
VRAM-resident model on another is a memory-controller and PCIe question, not a
matter of opinion.

## Background load: `hammer.py`

```bash
python3 hammer.py --host ROUTER --port 8080 --model OTHER-MODEL --concurrency 2 --duration 600
```

Saturates any OpenAI-compatible endpoint from the server side, so contention is
real and the measuring machine stays out of the result. Used as the `interference`
block of an `ab.py probe` spec.

## Useful flags

`--target host:port` (repeatable, or preset name) · `--host/--port/--scheme/--model` ·
`--api-key-env VAR` (key lives in the environment, never in files) · `--api-key KEY` (literal, less secure) ·
`--path-prefix PREFIX` (URL prefix before /v1/..., e.g. /api for OpenRouter) ·
`--tests name[,name]` or a suite json · `--depths 1024,8192,32768` ·
`--pp-sizes 512,2048,8192` · `--prompt-tokens N` (spec-decode prompt size) ·
`--repeat N` · `--timeout S` · `--gpu auto|off` ·
`--out DIR` · `--tag LABEL` (groups runs in summaries) · `--dry-run` · `--list-tests` · `--list-targets`

## Results

Each run appends to `results/runs.csv` (columns: ts, tag, run_id, target, model, test,
phase, depth, metric, value, first_token_s, detail, gpu_delta_mb, repeat, variant,
engine) and writes `results/run-<id>.json`. Compare runs, models and arms:

```bash
python3 summarize.py --group-by tag,model --last 6
python3 summarize.py --metric prefill_tps --out compare.md
python3 summarize.py --group-by variant --metric decode_tps   # A/B arms side by side
```

Cells with more than 10% spread between repetitions are marked `⚠`: raise `--reps`
or look for contention before quoting them. `mtp_acc` cells are ratios, not tok/s -
read them together with the `decode_tps` row of the same phase.

## Portability notes

- Runs anywhere python3 runs (WSL, Linux, macOS, Windows `py`/`python`).
- Add new suites by dropping a json into `tests/` (see `tests/README.md`), no code changes.
- Corpus text is synthetic with per-request nonces placed at the **front** of the
  prompt, so prompt caches cannot flatter results (a trailing nonce does nothing).
- `ab.py` hardcodes nothing: hosts, launch commands and teardown are operator
  templates in the spec file, which keeps engine comparisons portable across
  ssh-managed boxes, containers and local processes.
- GPU delta uses counters captured before/after each target run; on machines without
  vendor CLIs the field is simply empty.
