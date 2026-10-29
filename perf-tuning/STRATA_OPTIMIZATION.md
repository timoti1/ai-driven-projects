# Strata Engine: Optimization Notes (Qwen3.8-Flash-Next, AMD RX 9070)

Experiments from October 22, 2026: squeezing the most out of the Strata
engine on a consumer AMD build — what actually helps, what does not. All
numbers measured here; nothing borrowed from other write-ups.

## Hardware

| | |
|---|---|
| CPU | AMD Ryzen 7 5800 (8C/16T, **no AVX-512** — expert kernels run on AVX-2) |
| GPU | AMD Radeon RX 9070 (gfx1201, 16 GB), PCIe x16, measured link 28.3 GB/s |
| RAM | 64 GB (+8 GB swap) |
| Stack | ROCm/HIP, hipBLASLt with `gfx1201-hipblaslt-100401.txt` tuning |
| Strata | engine **v0.1.47** (BUILD.json: local-hip, gfx1201, src `ba8a2d35`), `--backend hip`; repo checkout v0.2.2 |

## Models

Both are Qwen3.8-Flash-Next (MoE, 256K context), Strata packs:

1. **flashS**: `Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S` (pack `swift-iq3_s`)
2. **flashX**: `Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS` (pack `sc117_iq3xxs`)

The MTP drafter head for both comes from the official
`Qwen/Qwen3.8-Flash-Next` checkpoint (pinned rev `de4b8e4d`, 31 tensors
~5.2 GB BF16, delivered by `tools/mtp_fetch.py` via HTTP range requests);
the drafter's experts are quantized to Q2_0 (`tools/mtp_pack.py --src ...
--experts q2_0`, `tools/mtp_rt.py` → `<mtp>/rt/`).

## Method

- 7 coding tasks (LRU cache, async bug hunt, Rust parser, SQL, Node.js
  refactor, Go rate limiter, CLI over a long file), `max_tokens 512`,
  `temperature 0`;
- metrics — **weighted decode tok/s** and MTP **acceptance rate**;
- one run per configuration → noise ±10–15 tok/s; trends are readable,
  exact numbers are not a benchmark.

## Defaults (as written by setup)

```text
--pack <pack> --native <gguf> --ple-gguf <gguf> --expert-profile expert-profile.bin
--expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5
--mtp <mtp>/rt --max-context 256000 --kv int8
```

Two defaults that we change:

- **the whole 256K KV cache lives in VRAM** (`--kv-resident 0`): ~3 GB
  carved out from under the experts before the first token;
- **the drafter's input norm is `pooled`**: one RMS over all four
  hyper-connection streams.

## What was swept (on IQ3_S)

| arm | flags | tok/s | acc |
|---|---|---|---|
| baseline | (defaults) | 51.0 | 0.72 |
| spec2 | `--spec 2` | 57.7 | 0.81 |
| spec3/6/8 | `--spec 3/6/8` | 56.4 / 57.3 / 58.9 | 0.78 / 0.65 / 0.65 |
| **kvres20480** | `--kv-resident 20480` | **63.8** | 0.71 |
| mtpq4 | `--mtp-q4 all` | 54.2 | 0.71 |
| reserve768 | `--vram-reserve-mib 768` | 57.2 | 0.74 |
| dvocaben | `--mtp-draft-vocab draft_vocab_en.bin` | 61.6 | 0.74 |
| hnormstream | `--mtp-hnorm stream` | 62.4 | 0.78 |
| kvres_spec2 | kvres + `--spec 2` | 63.3 | **0.82** |
| kvres_dven | kvres + en-vocab | 62.0 | 0.71 |
| kvres_minp07 | kvres + `--spec-min-p 0.7` | 60.0 | **0.85** |

## Final changes (vs defaults)

```text
+ --kv-resident 20480
+ --mtp-hnorm stream
```

### `--kv-resident 20480` — the main win (+25% on short tasks)

**Semantics**: 20480 is not kilobytes — it is the **number of KV cells
(context positions) per QSA layer kept in VRAM** (the minimum the engine
allows). The whole K/V is additionally held in pinned RAM (3.02 GB for
256K). The ~3 GB of VRAM this frees goes to the expert cache.

| | baseline | kv-resident 20480 |
|---|---|---|
| free VRAM at start | 6.8–6.9 GB | **9.9–10.0 GB** |
| expert slots (start) | ~2400–2800 | **~3600–4200** |
| decode hit rate | 56.8% | **68.8%** |
| IQ3_S, 7 tasks | 51.0 tok/s | **63.8 tok/s (+25%)** |
| IQ3_XXS, 7 tasks | 61.3 tok/s | **64.9 tok/s (+5.9%)** |

Long-context check (IQ3_S, single runs, decode tok/s):

| ctx | baseline | kvres 20480 | kvres 32768 |
|---|---|---|---|
| 32K | 51.6 | 46.7 | 63.3 |
| 64K | 42.7 | 68.5 | 74.6 |
| 128K | 61.1 | 69.8 | 49.5 |
| 246K | 59.1 | **66.0** | 66.9 |

Above 20480 tokens streaming kicks in but barely hurts: 95–98% of blocks
are still read from VRAM, only hundreds of MiB come from RAM per run. The
"it will collapse at 256K" fear did not materialize. The 32768 window
(setup's own default for ≥64K contexts) is statistically the same; 20480
leaves slightly more VRAM for experts.

### `--mtp-hnorm stream` (+20% over baseline on IQ3_S)

Not weights but a **normalization mode** of the existing MTP head: the
RMS is computed per hyper-connection stream (as in llama.cpp's qwen4exp
MTP graph) instead of one RMS over all four. No extra files needed.

### MTP options NOT worth taking

- **`--mtp-q4 all`** — 4-bit copies of the drafter's projections/head:
  +6% over baseline, well behind the other options.
- **`--mtp-draft-vocab .../draft_vocab_en.bin`** — narrow English
  vocabulary: good on its own arm (+21%), but never beats hnorm-stream
  in combinations.
- **Alternative quantization of the drafter's experts (q4_0/q8_0)** — the
  engine **rejects it**: `tools/mtp_rt.py` and the layout in
  `src/core/mtp.cpp` are Q2_0-only (BLOB = 3·(H·FF·18/64)). The GGUFs can
  be built (`mtp-q4_0.gguf` 1.6 GB, `mtp-q8_0.gguf` 2.9 GB), the rt
  format cannot — engine changes would be required.
- **Retrained MTP heads** (Jrouth refit0930, xkm 27B, etc.) — unavailable
  (404) at test time or tied to llama.cpp/C2T8.
- **Accuracy trade-off**: `--kv-resident 20480 --spec-min-p 0.7` gives
  the best acceptance (0.85) but is slower (60.0 vs 63.8) — skipped when
  speed is the goal.

## Final configs

**flashS — `strata-iq3_s.json`** (diff from defaults is the last four
args entries):

```json
{
    "exe": "/media/timoti/Data/repos/Strata/engine/strata",
    "args": [
        "--pack", "/media/timoti/Data/Strata-data/packs/swift-iq3_s",
        "--native", "/media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
        "--ple-gguf", "/media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
        "--expert-profile", "/media/timoti/Data/repos/Strata/data/expert-profile.bin",
        "--expert-cache", "auto",
        "--prefill", "auto",
        "--spec", "4",
        "--spec-min-p", "0.5",
        "--mtp", "/media/timoti/Data/Strata-data/mtp/rt",
        "--max-context", "256000",
        "--kv", "int8",
        "--kv-resident", "20480",
        "--mtp-hnorm", "stream"
    ],
    "cwd": "/media/timoti/Data/repos/Strata",
    "tokenizer": "/media/timoti/Data/Strata-data/packs/swift-iq3_s/tokenizer",
    "model_name": "qwen3.8-flash-IQ3_S",
    "log": "/media/timoti/Data/repos/Strata/strata-iq3_s.log",
    "lib_dirs": ["/opt/rocm/lib"],
    "port": 8085,
    "backend": "hip",
    "env": {
        "STRATA_HIPBLASLT_TUNING": "/media/timoti/Data/repos/Strata/tools/hip/gfx1201-hipblaslt-100401.txt",
        "STRATA_HIP_WMMA": "1"
    },
    "gpu": 1,
    "gpus_asked": true,
    "host": "0.0.0.0",
    "fit_max_tokens": true,
    "open_browser": false,
    "engine_silence_s": 900,
    "api_monitor": true
}
```

**flashX — `strata-iq3xxs-abl.json`** — same set, different paths:

```json
{
    "exe": "/media/timoti/Data/repos/Strata/engine/strata",
    "args": [
        "--pack", "/media/timoti/Data/Strata-data/packs/sc117_iq3xxs",
        "--native", "/media/timoti/Data/lmstudio/models/SC117-abl/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS-00001-of-00002.gguf",
        "--ple-gguf", "/media/timoti/Data/lmstudio/models/SC117-abl/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS-00002-of-00002.gguf",
        "--expert-profile", "/media/timoti/Data/repos/Strata/data/expert-profile.bin",
        "--expert-cache", "auto",
        "--prefill", "auto",
        "--spec", "4",
        "--spec-min-p", "0.5",
        "--mtp", "/media/timoti/Data/lmstudio/models/SC117-abl/strata/rt",
        "--max-context", "256000",
        "--kv", "int8",
        "--kv-resident", "20480",
        "--mtp-hnorm", "stream"
    ],
    "cwd": "/media/timoti/Data/repos/Strata",
    "tokenizer": "/media/timoti/Data/Strata-data/packs/sc117_iq3xxs/tokenizer",
    "model_name": "qwen3.8-flash-IQ3_XXS",
    "log": "/media/timoti/Data/repos/Strata/strata-iq3xxs-abl.log",
    "lib_dirs": ["/home/timoti/Downloads/llama-b1347-rocm-gfx120X"],
    "port": 8085,
    "backend": "hip",
    "env": {
        "STRATA_HIPBLASLT_TUNING": "/media/timoti/Data/repos/Strata/tools/hip/gfx1201-hipblaslt-100202.txt",
        "STRATA_HIP_WMMA": "1"
    },
    "fit_max_tokens": true,
    "open_browser": false,
    "engine_silence_s": 900,
    "api_monitor": true,
    "host": "0.0.0.0",
    "gpu": 1
}
```

## How to run

Directly (the server comes up on the config's `port`):

```bash
cd /media/timoti/Data/repos/Strata
.venv/bin/python serve/server.py --engine strata --config strata-iq3_s.json
# API: http://127.0.0.1:8085/v1/chat/completions  (OpenAI-compatible)
```

Or the engine binary alone, mirroring the `engine started` line:

```bash
/media/timoti/Data/repos/Strata/engine/strata --serve \
  --pack ... --native ... --expert-cache auto --prefill auto \
  --spec 4 --spec-min-p 0.5 --mtp <mtp>/rt \
  --max-context 256000 --kv int8 --kv-resident 20480 --mtp-hnorm stream
```

Confirm the flag took effect — the engine prints at startup:

```text
strata generate: KV streaming: 20480 of 256000 cells per QSA layer in VRAM, the K/V in 3.02 GiB of pinned RAM
```

## Caveats

- `--kv-resident N` (N ≥ 20480) = N context positions per QSA layer in
  VRAM; a context of ≤ N tokens is never streamed. The setting costs
  3 GB of pinned RAM when the host has it to spare.
- `--mtp-hnorm stream` is a mode, not weights; it works with any MTP head
  built into the `<mtp>/rt/` format.
- A/B plumbing choices (`lib_dirs`, hipBLASLt tuning files) turned out to
  be insignificant — they moved results within noise.
- Numbers come from one machine and one run per point. Re-measure on your
  own hardware. In particular `--kv-resident`: on other GPUs/buses the
  balance between "expert slots vs KV streaming" may shift (Strata's own
  docs carry Radeon measurements that came out "flat").
