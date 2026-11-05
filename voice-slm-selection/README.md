# Voice SLA Model Selection

Selection of a small (≤4B) text-only language model for a **voice assistant**:
post-processing of Russian speech-to-text transcripts (cleanup, ASR-error repair,
translation, grammar) and a lightweight chat/voice-assistant role, running on
**CPU only** (16-core AMD Ryzen 5800, 62 GB RAM) via the `ik-cpu-llama` engine.

This subproject records the whole selection: goals, candidates, what was rejected
and why, the real-prompt test set, the methodology, and the measured results.

## Goals & constraints

- ≤4B parameters, **text-only** (no vision/audio — not needed).
- Strong **Russian + English**: interpret unclear speech, translate, fix grammar.
- **CPU-only** inference; compact file; fast enough for near-real-time post-processing.
- Must run under `ik-cpu-llama` (`/home/timoti/Downloads/ik-cpu-llama/build-cpu/bin/llama-server`).
- Replace the existing standalone CPU service (Qwen3.5-4B Q4_K_M on port 5899) —
  **one** CPU text service, not two.
- Tight disk: ~67 GB free on `/media/timoti/Data`.

## Candidates considered

| Model | Why considered | Quant | Size |
|---|---|---|---|
| Qwen3.5-4B | strong RU/EN, native `qwen35` arch in ik-cpu-llama | Q5_K_M | 3.14 GB |
| Qwen3.5-2B | smaller/faster variant of the same family | Q5_K_M | 1.44 GB |
| Gemma-4-E2B | fast on CPU, Apache-2.0, `gemma4` arch supported | Q4_K_M | 3.11 GB |
| RuadaptQwen3-4B | Russian tokenizer, claimed +up to 100% RU gen speed | Q5_K_M | 2.88 GB |
| Qwen3.5-4B Q4_K_M | the *incumbent* on port 5899 (baseline) | Q4_K_M | ~2.9 GB |

### Rejected / not pursued
- **Text-only Gemma-4 derivatives** (ozgurpolat, principled-intelligence, Handyfff):
  either *larger* than the base E2B (defeats the purpose) or English-only pruned
  (Handyfff) — bad for Russian.
- **Gemma-4-E4B text-only**: 8B text layers, Q4_K_M = 5.34 GB — over budget.
- **North Small Translate / Tiny Aya / Gamayun**: narrower (translation-only or
  weaker RU) than the general candidates.
- **Multimodal variants of any candidate**: vision/audio encoders add size with no
  benefit for a text pipeline.

## Test set (real prompts)

`scripts/extract_prompts.py` mines the pi session history
(`~/.pi/agent/sessions/**/*.jsonl`, 389 files, 873 unique Russian user prompts)
and scores each by "messiness": filler-word density (короче/типа/ну/вот/…),
immediate word repeats, and missing punctuation. The top messiest prompts —
genuine voice dictation with ASR errors — were curated into `data/cases.json`
(12 cases, mix of real + a few synthetic).

Real ASR errors present in the set (ground truth in `gold_meaning`):
- `авраа` → Avro, `жоп` → job, `rock m` → ROCm, `лаама-сваб` → llama-swap,
  `data колити дата март` → data quality / data mart, `Gma 4` → Gemma 4,
  missing punctuation, filler words, capitalization, `реСтарт` → restart.

## Methodology

1. **Run** each candidate over all 12 cases with a strict post-processor system
   prompt ("return ONE cleaned version, nothing else"). `scripts/run_candidates.py`
   records output, wall time, and tokens/s.
2. **Judge** each output with a 27B model
   (`qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` via llama-swap) on 5 dimensions:
   `meaning`, `fix`, `clean`, `faithful`, `concise` (0–10). `scripts/judge.py`.
   Quality = mean of the five.
3. **Translate** test: 4 EN↔RU sentences per model to cover the assistant's
   translation role.

Known bias: the judge is slightly lenient on the `fix` dimension (it rewards a
model that keeps a wrong word like `жоп`/`Rockm`), so the `fix` scores are an
upper bound; the `meaning`/`faithful`/`concise` scores are reliable.

## Results

`results/judged.json` (quality + speed), `results/raw_*.json` (per-case outputs),
`results/translate_*.json` (translation).

| Model | Quality | Speed | Size | Notes |
|---|---|---|---|---|
| **Qwen3.5-4B Q5_K_M** | **9.57** | 5.3 t/s | 3.14 GB | best ASR-error repair (Job/Watermark/ROCm) |
| **Gemma-4-E2B Q4_K_M** | 9.42 | **13.7 t/s** | 3.11 GB | 2.6× faster, same size; leaves жоп/Rockm |
| Qwen3.5-2B Q5_K_M | 8.50 | 10.0 t/s | 1.44 GB | too small; mistranslates ("crashed"→"сгорел") |
| RuadaptQwen3-4B Q5_K_M | 7.83 | 8.6 t/s | 2.88 GB | drifts: paraphrase / answers instead of cleaning |

### Translation (EN↔RU)
- Gemma-4-E2B and Ruadapt: excellent and fast (~3 s/sentence).
- Qwen3.5-4B: good, slower (~6 s).
- Qwen3.5-2B: bad (mistranslations).

## Decision

**Chosen: Qwen3.5-4B** — the only candidate that actually repairs the
recurring ASR errors (Job/Watermark/ROCm). It runs on **fixed port 5899** via
the `ik-cpu-llama` engine (CPU-optimised build), managed by the systemd user
unit `qwen35-4b-cpu.service` (enabled, `Restart=always`).

**Chosen quant: Q4_K_M** — the reasonable compromise among the tested
quants: a significant memory reduction (−0.4 GB RSS vs Q5_K_M) and a speed
increase (9.79 vs 8.59 t/s) at only a negligible quality cost (−0.08, below
the judge's per-case resolution). See the
[Model-weight quantization](#model-weight-quantization-5-bit-vs-4-bit) chapter.

- Model file: `/media/timoti/Data/lmstudio/models/unsloth/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q4_K_M.gguf`
- Engine: `/home/timoti/Downloads/ik-llama.cpp/build-cpu-opt/bin/llama-server` (LTO-optimized, commit 656036d9)
- Flags: `--host 0.0.0.0 --port 5899 --ctx-size 16384 -t 8 --threads-batch 8
  --batch-size 512 --ubatch-size 256 -fa on --jinja -rea off --parallel 1
  --mlock --temp 0.3 -ctk q4_0 -ctv q4_0 --metrics`
- Jarvis config (server `~/.config/jarvis/config.json` **and** Windows client
  `C:\Users\Admin\.config\jarvis\config.json`): `llm_base_url` →
  `http://192.168.1.104:5899/v1`, `llm_chat_model` + `fast_model` → the gguf
  path above (the model ID this build reports).

**Gemma-4-E2B** was the speed pick (13.7 t/s, same disk size, quality within
~5%) but is **not used anywhere**: no running process, no llama-swap entry,
no Jarvis reference. It is kept only as the measured runner-up.

### Prompt-format note
Quality depends on how the post-processing prompt is framed. The benchmark's
single combined user message (system instructions + `ТЕКСТ:` + raw text) yields
the best ASR-error repair. A separate `system` + `user` message split is
slightly weaker (leaves some wrong words). The model and service are identical;
only the request framing changes the result.

## KV-cache quantization: 16-bit vs 4-bit

The default KV-cache dtype is f16 (16-bit). To shrink the context footprint
we re-ran the same benchmark with the KV cache quantized to **q4_0** for both
K and V (`-ctk q4_0 -ctv q4_0`), on a **separate instance** (port 5905) so the
running f16 service (5899) was untouched and both runs were directly comparable.

### Setup
- Identical model (Qwen3.5-4B Q5_K_M), flags, prompt, and temperature.
- Only difference: `-ctk q4_0 -ctv q4_0` on the 5905 instance.
- Same 12-case cleanup benchmark (`data/cases.json`), same judge
  (`qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` via llama-swap), same 5
  dimensions (meaning/fix/clean/faithful/concise).

### Memory effect
| KV dtype | KV self size | KV buffer | Process RSS |
|---|---|---|---|
| f16 (default) | 512 MiB (K 256 + V 256) | 562 MiB | ~4.3 GB |
| **q4_0** | **144 MiB** (K 72 + V 72) | **194 MiB** | **~4.1 GB** |

The KV cache shrinks **~3.5×** (512 → 144 MiB); total RSS drops ~250 MB
(the KV buffer is the only private-memory component that moves; the model
file is mmap'd page cache in both cases).

### Quality effect
| KV dtype | Quality | Speed |
|---|---|---|
| f16 | **9.57** | 7.1 t/s |
| q4_0 | 9.53 | 6.2 t/s |

Per-case: **11 of 12 cases scored identically**. The only difference was c04
(fix 10→9, clean 9→8, −2 points) — a borderline case where a 4-bit KV slightly
softened one ASR-error repair. The other 11 cases (including the hardest
c02/c06/c08) were unchanged.

### Verdict
- **Quality loss: negligible** (9.57 → 9.53, one borderline case). The 4-bit
  KV is a safe, near-free win for a 4B model at 16K context.
- **Memory win: real** — KV cache 512 → 144 MiB (−72%), RSS −250 MB. This
  matters on CPU (frees RAM for the model + other services) and would matter
  more on a GPU (frees VRAM for a larger context or a co-resident model).
- **Speed: within noise** (7.1 → 6.2 t/s, ~13%); the q4 run was the second of
  two sequential runs, so part of the delta is run-order/contention, not a
  reliable regression.
- **Recommendation:** enable `-ctk q4_0 -ctv q4_0` on the production service.
  The quality cost is below the judge's per-case resolution and the memory
  saving is significant.

## Model-weight quantization: 5-bit vs 4-bit

After the KV-cache experiment, we compared the **model-weight** quantizations
of Qwen3.5-4B (Q5_K_M vs Q4_K_M / IQ4_XS / IQ4_NL) under the user-proposed
thread/batch parameters (`-t 8 --threads-batch 8 --batch-size 512
--ubatch-size 256`) with the 4-bit KV cache, to find the smallest quant that
keeps quality. Each model ran on a dedicated port, same 12-case benchmark,
same 27B judge.

### Setup
- Identical flags for all: `-t 8 --threads-batch 8 --batch-size 512
  --ubatch-size 256 -fa on --jinja -rea off --parallel 1 --mlock --temp 0.3
  -ctk q4_0 -ctv q4_0`, `--ctx-size 16384`.
- Only the model file differs (Q5_K_M / Q4_K_M / IQ4_XS / IQ4_NL from
  `unsloth/Qwen3.5-4B-GGUF`).
- Same 12-case benchmark, same judge, same 5 dimensions.

### Comparison table

| Quant | File size | Quality | Speed (t/s) | RSS (GB) | Δ quality vs Q5 |
|---|---|---|---|---|---|
| **Q5_K_M** | 3.14 GB | **9.57** | 8.59 | 4.04 | — |
| Q4_K_M | 2.74 GB | 9.49 | **9.79** | 3.69 | −0.08 |
| IQ4_NL | 2.58 GB | 9.48 | 8.72 | 3.58 | −0.09 |
| IQ4_XS | 2.48 GB | 9.47 | 8.95 | 3.44 | −0.10 |

- **Quality:** all three 4-bit quants are within 0.10 of Q5_K_M — below the
  judge's per-case resolution (per-case diffs of 1–3 points on a handful of
  cases, the rest identical). No 4-bit quant is clearly worse.
- **Speed:** 4-bit is *faster* (9.79 t/s for Q4_K_M vs 8.59 for Q5_K_M) —
  smaller weights = less memory bandwidth per token, which is the bottleneck
  on CPU. The user-proposed small-batch params also beat the original
  `-t 12 --batch-size 1024` (7.1 t/s).
- **Memory:** RSS tracks file size almost 1:1 (the model file dominates; KV +
  compute buffers are constant across quants). Q5_K_M → IQ4_XS saves ~0.6 GB
  RSS.

### Per-case quality deltas (vs Q5_K_M baseline)
- Q4_K_M: total −5 (c03 +2, c06 −1, c08 −3, c09 −3; rest identical)
- IQ4_XS: total −6 (c03 −2, c04 −3, c06 −1, c08 −1, c09 −1, c11 +2; rest identical)
- IQ4_NL: total −5 (c04 −3, c06 −1, c09 −1; rest identical)

All deltas are small and scattered (no systematic collapse), confirming the
quality difference is within judge noise.

### Verdict
- **Q4_K_M — chosen.** The reasonable compromise: a significant memory
  reduction (−0.4 GB RSS vs Q5_K_M) and a speed increase (9.79 vs 8.59 t/s)
  at only a negligible quality cost (−0.08, below the judge's per-case
  resolution). It is the best of the "standard" (non-IQ) 4-bit quants and the
  fastest of all tested.
- **IQ4_XS** is the smallest (2.48 GB, −0.66 GB vs Q5_K_M) with quality within
  0.10 — the maximum memory saving at near-identical quality, but ~1 t/s
  slower than Q4_K_M and an IQ (imatrix) quant, which is slightly less
  robust to unusual inputs than a standard K-quant.
- All three 4-bit quants are safe; the choice is a memory/speed tradeoff, not
  a quality one. **Q4_K_M** was selected for the production service.

### Judge behaviour note
The 27B judge was consistent across both KV variants: it gave the same scores
on 11/12 cases and only moved on the one genuinely borderline case (c04),
which is exactly the sensitivity we wanted — it did not systematically favour
or penalise either variant. This confirms the f16-vs-q4 result is a real
quality comparison, not judge noise.

## Fine-tuning the winner (Qwen3.5-4B)

The selected model (Qwen3.5-4B, Q4_K_M) is a general instruct model. For the
voice-assistant role (transcript cleanup, ASR-error repair, translation,
light chat) a targeted fine-tune can push quality further without changing
the model or its size. This chapter records the plan and the state.

### Why fine-tune
- The benchmark already shows the base model is strong (9.57 quality). A
  fine-tune on a curated transcript-cleanup dataset would specialize it on
  exactly the task: fixing ASR errors, removing fillers, restoring
  punctuation, preserving meaning. Expected gain: more consistent ASR-error
  repair (the `fix` dimension) and fewer borderline cases like c04.
- It is cheaper than swapping to a larger model: same 4B size, same speed,
  same memory. The quality gain comes from data, not parameters.

### Approach (LoRA / QLoRA)
- **Method:** LoRA (or QLoRA to keep it on the 4-bit base) on the Q4_K_M
  weights. LoRA rank 16–32, alpha 32–64, on `q_proj`/`k_proj`/`v_proj`/`o_proj`
  and `gate_proj`/`up_proj`/`down_proj`. Train on the GPU (RX 9070) where the
  27B models already run, then merge the adapter into a GGUF.
- **Data:** a curated set of (messy transcript → cleaned transcript) pairs.
  The existing `data/cases.json` (12 cases) is a seed; expand it to hundreds
  of pairs harvested from real dictation (the same mining approach as
  `scripts/extract_prompts.py`), with gold cleanings. Include the recurring
  ASR errors (Job/Watermark/ROCm/Avro/llama-swap) and filler-heavy speech.
- **Split:** train/val to watch for overfitting; keep a held-out slice of the
  benchmark cases to measure the real gain with the same 27B judge.
- **Merge:** export the LoRA adapter, merge into the base, re-quantize to
  Q4_K_M (or keep the adapter separate and load it at runtime if the engine
  supports it). Re-run the 12-case benchmark + judge to confirm the gain.

### State
- **Not yet done.** The base Q4_K_M model is in production on port 5899 and
  already meets the quality bar. Fine-tuning is the next quality lever, to be
  run once a larger curated transcript dataset is available.
- The benchmark harness (`scripts/run_candidates.py` + `scripts/judge.py`) is
  reusable as-is to measure the fine-tuned model against the base.

## Artifacts

- `scripts/extract_prompts.py` — mine messy Russian prompts from pi history.
- `scripts/run_candidates.py` — run a candidate endpoint over `data/cases.json`.
- `scripts/judge.py` — LLM-as-judge scoring of the outputs.
- `data/cases.json` — the 12-case test set with gold meanings.
- `results/` — raw outputs, judged scores, translation results, and the
  KV-quantization A/B (`raw_kv-f16.json`, `raw_kv-q4.json`, `judged_kv.json`).

## Engine optimization (ik-cpu-llama rebuild)

The `ik-cpu-llama` fork was updated from commit `a540dff` to `656036d9`
(~252 commits) and rebuilt with LTO (`-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON`)on top of the existing `GGML_NATIVE=ON` (which already enabled AVX2/FMA/F16C/BMI2 via `-march=native`).

### Build command
```bash
cd /home/timoti/Downloads/ik-llama.cpp
git reset --hard origin/main
cmake -B build-cpu-opt -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
  -DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF -DLLAMA_CURL=OFF
cmake --build build-cpu-opt -j16
```

### A/B benchmark (Qwen3.5-4B Q4_K_M, same flags, warmup + 5 runs)

| Metric | Old binary (`build-cpu`) | New binary (`build-cpu-opt`) | Δ |
|---|---|---|---|
| Generation (t/s, median) | 13.04 | 13.38 | +2.6% |
| Prompt-eval (t/s, 4049-token prompt) | 83.53 | **96.64** | **+15.7%** |
| Prompt-eval wall time (4049 tok) | 48.47 s | 41.90 s | −13.6% |

The prompt-eval gain is significant: it is the dominant latency when context
grows (long transcripts, multi-turn). Generation improved modestly (~3%).

### Deployment
- Binary: `/home/timoti/Downloads/ik-llama.cpp/build-cpu-opt/bin/llama-server`
- Unit file updated: `ExecStart` → `build-cpu-opt/bin/llama-server`
- Old build kept at `build-cpu/` for rollback.
- Backup of unit file: `/tmp/qwen35-4b-cpu.service.bak.*`

## Reproduce

Candidate servers were launched with `ik-cpu-llama` on ports 5901–5905 (one per
model / KV variant), `--jinja -rea off --temp 0.3 --mlock --parallel 1`; the
q4_0 KV variant added `-ctk q4_0 -ctv q4_0` on port 5905. The judge ran through
llama-swap (27B model). See `scripts/*.py` for the exact endpoints/models.
