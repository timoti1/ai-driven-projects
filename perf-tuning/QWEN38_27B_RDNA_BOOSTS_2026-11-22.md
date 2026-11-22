# Qwen3.8-27B (dense, IQ3_XXS + MTP): moving from Vulkan to `rdna-boosts` HIP

Investigated 2026-11-22 on the two-GPU host, model on the Gigabyte card
(`0000:0b:00.0`, x16). Companion tooling: [`../perf-bench`](../perf-bench). Related:
[INKLING2_MINI_2026-11-22.md](INKLING2_MINI_2026-11-22.md),
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md).

**TL;DR**

- **39.9 → 78.4 tok/s** by running this model on the `rdna-boosts` HIP build instead of the
  Vulkan build, with the MTP drafter enabled. Prefill went 388 → 709 tok/s.
- MTP is almost free on the HIP build (**+66%**: 40.8 → 67.9) and nearly worthless on
  Vulkan (**+6%**: 37.8 → 39.9). The engine choice is what unlocks the drafter.
- Optimum: `--spec-type draft-mtp --spec-draft-n-max 3 -ub 1024`. Longer draft blocks lose.

## 1. Engine matrix (code prompt, ctx 120000, greedy)

| Engine | Device | Drafter | tg tok/s | pp tok/s | Acceptance |
|---|---|---|---|---|---|
| Vulkan (`llama-latest/build`, custom Mesa ICD) | Vulkan1 | MTP n3 | 39.9 | 388 | 50% |
| Vulkan | Vulkan1 | none | 37.8 | 465 | — |
| mainline HIP (`llama-latest/build-hip`) | ROCm0 | MTP n3 | 43.6 | 543 | 49% |
| `llama-rdna3` fork (Inkling fusions) | ROCm0 | MTP n3 | 43.7 | 558 | 49% |
| **`rdna-boosts` r275 (HIP, stew675)** | **ROCm0** | **MTP n3** | **67.9** | **709** | 48% |
| `rdna-boosts` r275 | ROCm0 | none | 40.8 | 772 | — |

Two independent effects: the drafter's verify batch is cheap on `rdna-boosts` and expensive on
Vulkan, and prefill is 1.5–1.8× faster on HIP (which matters more than decode for agent
workloads that re-read a long conversation). Without any drafter `rdna-boosts` still wins on
prefill (772 vs 465), so the engine choice stands alone.

The Inkling fusion fork matches mainline on a dense model (43.7 vs 43.6): its fusions are
model-specific, and its mmvq retune targets gfx1100, not RDNA4.

## 2. Flag sweep (`rdna-boosts`, MTP, ctx 120000)

| Variant | tg tok/s | Acceptance | VRAM |
|---|---|---|---|
| n-max 2 | 67.6 | 59% | 14.4 GiB |
| **n-max 3** | **67.9** | 48% | 14.5 GiB |
| n-max 4 | 62.2 | 39% | 14.7 GiB |
| n-max 6 | 53.3 | 29% | 14.9 GiB |
| `-ub 512` | 66.3 | 47% | 14.2 GiB |

KV quantisation changed nothing in speed here either (q4_0 vs q8_0); q4_0 is kept so 120k
context fits in 14.5 GiB.

## 3. Configuration applied

`llama-swap` profile `qwen3.8-27b-IQ3XXS-Uncensored`:

```
${rdna-boosts}   # /home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server
  --model …-MTP.gguf  --mmproj …-Q5_K-MIX.gguf
  --device ROCm0  -ngl 99  --flash-attn on  --parallel 1
  --spec-type draft-mtp  --spec-draft-n-max 3
  --batch-size 2048  --ubatch-size 1024  --ctx-size 120000
  -ctk q4_0  -ctv q4_0  --jinja  --cache-ram 0
env: CUDA_VISIBLE_DEVICES=  HIP_VISIBLE_DEVICES=1
     LD_LIBRARY_PATH=/opt/rocm/lib  HSA_OVERRIDE_GFX_VERSION=12.0.1
```

Verified through the API after the switch: **tg 78.4 tok/s, acceptance 62%**, 120k context,
`--spec-type draft-mtp`, 14.5 GiB VRAM.

Pitfall: the previous profile used `--device Vulkan1` with
`VK_DRIVER_FILES=/home/timoti/mesa-build/radeon_icd.json` and `RADV_PERFTEST=coop_matrix`.
All three must be removed when switching to HIP (`--device ROCm0` + the environment above),
otherwise the server exits with `no ROCm-capable device is detected`.
