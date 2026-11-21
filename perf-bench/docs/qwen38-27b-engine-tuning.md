# Qwen3.8-27B (dense, IQ3_XXS + MTP): engine and flag tuning

Same hardware and protocol as `docs/inkling-2-mini-tuning.md`: `ryzen5800`, Gigabyte RX 9070
(`0000:0b:00.0`), greedy decoding, code-shaped prompt, 256 generated tokens, server `timings`.
Model: `Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored-MTP.gguf` (dense 27B, MTP heads inside the file).

## Result

**39.9 → 78.4 tok/s** by moving the model from the Vulkan build to the HIP `rdna-boosts` build with
the MTP drafter enabled (`--spec-type draft-mtp --spec-draft-n-max 3`).

## Why: MTP pays off on HIP, not on Vulkan

| Engine | Device | Drafter | tg tok/s | pp tok/s | Acceptance |
|---|---|---|---|---|---|
| Vulkan (`llama-latest/build`, custom Mesa ICD) | Vulkan1 | MTP n3 | 39.9 | 388 | 50% |
| Vulkan | Vulkan1 | none | 37.8 | 465 | — |
| mainline HIP (`llama-latest/build-hip`) | ROCm0 | MTP n3 | 43.6 | 543 | 49% |
| fused fork (`llama-rdna3`, inkling fusions) | ROCm0 | MTP n3 | 43.7 | 558 | 49% |
| **`rdna-boosts` r275 (HIP, stew675)** | **ROCm0** | **MTP n3** | **67.9** | **709** | 48% |
| `rdna-boosts` r275 | ROCm0 | none | 40.8 | 772 | — |

Two separate effects:

1. **MTP is nearly free on `rdna-boosts`** (+66%: 40.8 → 67.9) and almost worthless on Vulkan
   (+6%: 37.8 → 39.9). The verify batch is what the drafter costs; on the Vulkan build the extra
   columns of the verify matmul are expensive, on the HIP build they are not.
2. **Prefill is 1.5–1.8× faster on HIP** (388 → 709 tok/s), which matters more than decode for
   agent workloads that re-read a long conversation.

The same `rdna-boosts` binary also wins on prefill without any drafter (772 tok/s), so the engine
choice is independent of speculation.

## Flag sweep (`rdna-boosts`, MTP, ctx 120000, `-ub 1024`)

| Variant | tg tok/s | Acceptance | VRAM |
|---|---|---|---|
| n-max 2 | 67.6 | 59% | 14.4 GiB |
| **n-max 3 (default)** | **67.9** | 48% | 14.5 GiB |
| n-max 4 | 62.2 | 39% | 14.7 GiB |
| n-max 6 | 53.3 | 29% | 14.9 GiB |
| `-ub 512` | 66.3 | 47% | 14.2 GiB |

n-max 2–3 is the optimum: longer draft blocks raise the verify cost faster than they raise accepted
tokens per step. `-ub 1024` beats 512 slightly and costs ~0.3 GiB.

## What did not help

- Vulkan → HIP alone, without the drafter: 37.8 → 40.8 (+8%), the large part of the win is the
  combination.
- The Inkling fusion fork: its fusions are Inkling-specific; on a dense 27B it matches mainline
  (43.7 vs 43.6). Its generic parts (mmvq table, q8_1 cache) are tuned for gfx1100 and do not move
  RDNA4.
- KV quantisation: q4_0 vs q8_0 changed nothing in speed on this model either; q4_0 is kept to fit
  120k context in 14.5 GiB.

## Final configuration

`llama-swap` profile `qwen3.8-27b-IQ3XXS-Uncensored` now runs:

```
${rdna-boosts}                        # /home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server
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

Note: the previous profile used `--device Vulkan1` with `VK_DRIVER_FILES=/home/timoti/mesa-build/radeon_icd.json`
and `RADV_PERFTEST=coop_matrix`; those three settings must be removed when moving to the HIP build
(`--device ROCm0` + the HIP environment above), otherwise the server exits with
`no ROCm-capable device is detected`.
