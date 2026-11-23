# Inkling 2 Mini and Qwen3.8-Flash-Next on AMD RDNA4: five engines, one card

Investigated 2026-11-23 on the two-GPU host, all measurements on the **Gigabyte RX 9070**
(`0000:0b:00.0`, `HIP_VISIBLE_DEVICES=1`, PCIe 4.0 x16, 15.9 GiB usable). The question came
from an Unbiased Bob video recommending `maya-ik2` + Unsloth `UD-Q4_K_XL` for Inkling 2 Mini,
with "not llama.cpp" as the headline. Companion tooling: [`../perf-bench`](../perf-bench).
Related: [INKLING2_MINI_2026-11-22.md](INKLING2_MINI_2026-11-22.md) (the same model on the
Sapphire card and the two-card router), [STRATA_OPTIMIZATION.md](STRATA_OPTIMIZATION.md),
[AVALON_OPTIMIZATION_COMPARISON.md](AVALON_OPTIMIZATION_COMPARISON.md).

## TL;DR

- **The fastest Inkling 2 Mini on this card is `strata-inkling` (Strata 0.2.20) with the
  `SQ-10` pack**: **59.6 tok/s** decode / **2 476 tok/s** prefill at 1.5 k, and it is the
  only configuration that does *not* collapse at depth — **37.0 tok/s at a 62 756-token
  prompt**, where the 13.4 GiB `SQ-15` pack drops to 15.3 and `maya-ik2` to 32.9.
- **`maya-ik2` does run on this AMD card — I ported it** (it ships CUDA-only). The port is
  correct (its own FP64 kernel reference suite passes) but, at 16 GB, it loses to the
  Strata pack build: 49 tok/s short, **32.9 tok/s at 62 k**, prefill 924 vs 2 124.
- **The GGUF is the slow path for `strata-inkling`.** With `UD-Q4_K_XL` the engine reports
  *"native lossless GGUF_RAW GPU kernels active for 512/3072 experts"* and manages 29.5 tok/s.
  The `.strata` packs are the intended format, and the pack size is what decides speed:
  **SQ-10 (9.75 GiB) > SQ-15 (13.4 GiB) > SQ-20 (needs 24 GiB)**.
- **The DSpark drafter is worthless on this card in every engine**: 56.5 → 56.3 tok/s on
  Strata, 48.7 → 47.1–49.2 on maya-ik2, and forcing it (`IK2_DRAFT_ADAPT=0`) changes
  nothing. With ~78 % of the experts resident, a verify window never pays.
- **Two GPUs are slower than one**, even with all 14.7 GiB of experts cached:
  **29.8–33.1 tok/s** against 49 on a single card — the chipset x2 slot costs more than the
  misses it removes.
- **For Qwen3.8-Flash-Next the old engine wins**: Strata **0.2.15** does 70.9 tok/s (IQ3_S)
  and 76.8 (IQ3_XXS); 0.2.20 does 63.9 / 62.1 with the same config, and refuses to run
  without its own expert profile. The 0.2.20 entries stay as A/B twins only.
- **UnbiasedStrata adds nothing here and has been removed** from the host: its engine is a
  PolyStrata 0.1.45-poly.1 vintage (prefill 723–848 vs 1 191–1 234 for 0.2.15), its Inkling
  engine on Linux is CPU + Metal only, and its `src/ik2` is the same CUDA source that needed
  porting in the first place.
- **KV cache**: `fp8` (8-bit E4M3) is the right choice everywhere; 16 KB/token in maya-ik2,
  and `k8v4`/`k8v8` are unusable on HIP (upstream #6681: they allocate *more* than fp16 and
  OOM earlier). There is no 4-bit KV in maya-ik2 at all.

## 1. The engines in play

| Engine | Upstream | Backend on this box | Runs Inkling? |
|---|---|---|---|
| **`strata-inkling` 0.1.66** (Strata 0.2.20) | Niko1221/Strata | HIP, RDNA4 WMMA + DP4A | **yes — `.strata` packs, this is the winner** |
| `strata` 0.1.66 (same release, Qwen family) | Niko1221/Strata | HIP | Qwen only |
| `strata` 0.1.5x (Strata 0.2.15, current production) | Niko1221/Strata | HIP | **no — not a single "inkling" string in the tree** |
| `maya-ik2` | alesha-pro/maya-inkling-mini (CUDA only) | **HIP, ported today** | yes, GGUF `UD-Q4_K_XL` only |
| PolyStrata `strata` (UnbiasedStrata) | robertkarl/UnbiasedStrata | HIP on gfx1201 | no (its Inkling engine is CPU/Metal) — **deleted after measurement** |
| `fusion-llama` (GodGMN `inkling-rdna3` + PR #32218) | existing llama-swap profiles | HIP | yes, last week's best |

## 2. Porting `maya-ik2` to HIP (the work behind the numbers)

Upstream builds it for CUDA only; the HIP path in its CMake was a non-linking "spike"
(`STRATA_HIP_IK2_SPIKE`, *"compile the kernels as HIP to enumerate port work"*). Changes,
all guarded by `__HIP_PLATFORM_AMD__` in `src/ik2/ik2_kernels.cu`:

| CUDA primitive (what the kernels call) | HIP replacement |
|---|---|
| `mma.sync.aligned.m16n8k16` | quad shuffles + `__hmul2`, FP32 sums, same A/B/C fragment layout |
| `ldmatrix.sync.aligned.m8n8.x4` (+ `.trans`) | shared reads at addresses gathered with `__shfl_sync` |
| `cp.async.cg/ca` + `commit`/`wait_group` | plain 16/4-byte copies, waits are no-ops (plus one extra `__syncthreads()` before the next tile's copies land) |
| `mul.rn.f16x2` / `sub.rn.f16x2` | `__hmul2` / `__hsub2` |
| `__cvta_generic_to_shared`, `"+f"` asm constraints | generic casts, `"v"` integer constraints |

Two further findings:

- The fused prefill-attention kernel needs **88 KB of shared memory**; gfx12 allows 64 KB per
  workgroup, so it cannot run — the engine is driven with `IK2_FLASH=0` (attention through the
  logits path).
- Correctness gate: the repo's own `ik2_kernels_test` compares kernels against a **float64
  reference**; decode/multi-query attention (FP32/FP16/**FP8 KV**), routing, NVFP4 and Q8_0
  experts all pass on gfx1201. The `attn_flash` case is the one that cannot launch.

Notes: `maya-inkling-mini/HIP-PORT-gfx1201.md`.

## 3. Inkling 2 Mini: the full matrix

All rows: Gigabyte card, `--kv fp8` where the engine allows it, single stream, temperature 1.0,
`reasoning_effort none`. "CLI" rows are the engine's own `--bench` (no 120 k reservation);
"server" rows run through llama-swap with the KV reserved for 120 k — that reservation is what
makes the difference between the two columns, not the engine.

| Engine / file | ctx | 1.5–2 k prompt | 32 k | 62.7 k |
|---|---|---:|---:|---:|
| **`strata-inkling` + `SQ-10` pack, CLI** | — | **59.6 tok/s · 2 476 pp** | **29.2 · 1 758** | 18.4 · 1 387 |
| **`strata-inkling` + `SQ-10` pack, server** | **120 k** | **47–48 · 2 124** | — | **37.0 · 1 341** |
| `strata-inkling` + `SQ-15` pack, CLI | — | 56.5 · 2 071 | 21.3 · 1 439 | 14.5 · 1 054 |
| `strata-inkling` + `SQ-15` pack, server | 120 k | 50.5 · 1 651 | — | 15.3 · 1 016 |
| `strata-inkling` + GGUF `UD-Q4_K_XL` (best of 5 placements) | — | 29.5 · 581 | — | — |
| `maya-ik2` (HIP port) + GGUF, server | 131 k | 49.1 · 870–924 | — | 32.9 · 621 |
| `maya-ik2` + GGUF, small context | 16 k | 49.5 · 710–952 | — | — |
| `maya-ik2`, 2 GPUs, every expert cached | 128 k | 29.8–33.1 · 632–980 | — | — |
| `fusion-llama` fork + `UD-IQ3_XXS` (existing profiles) | 2 × 100 k | 54.8 · 1 014 | — | — |

Depth decay on the winner, through llama-swap: **1.5 k → 59.6, 32 k → 29.2, 64 k → 37.0**
(the last column is the server run, which holds more KV in VRAM than the CLI one — the two
rows are not the same reservation, the shape of the curve is).

Why SQ-15 dies at depth and SQ-10 does not: at 120 k the KV cache is ~2 GiB in FP8. SQ-15
(13.4 GiB) leaves nothing for it, `--kv-offload auto` pushes it to host memory and decode
falls to 15 tok/s. SQ-10 (9.75 GiB) keeps it on the card. Forcing `--kv-offload off` at 64 k
on SQ-15 → `alloc_gpu_buffer: out of memory`, which pins the explanation down.

## 4. Qwen3.8-Flash-Next: which Strata

Same pack, MTP, exponent profile, `--kv int8`, 200 k context, same card.

| Engine | IQ3_S | IQ3_XXS |
|---|---|---|
| **Strata 0.2.15 (production)** | **70.9 tok/s · 1 191–1 234 pp** | **76.8 tok/s (93.8 on code) · 1 271–1 326 pp** |
| Strata 0.2.20 | 63.9 · 910–1 207 | 62.1 (90.4 on code) · **1 293–1 355 pp** |
| UnbiasedStrata (HIP, own env) | 69.5 · 770–848 | — |
| UnbiasedStrata (HIP, plain) | 67.3 · 709–772 | — |

Reading: 0.2.20 is ~10 % slower on Qwen with a 0.2.15-era expert profile, and it **refuses to
start without one** (*"verify needs the profile-filled VRAM expert tier"*) — so moving Qwen to
0.2.20 requires regenerating that profile with 0.2.20's own tooling. Until then 0.2.15 stays
production and 0.2.20 runs only as the `-v0220` twins.

## 5. What was tested and rejected

| Idea | Result |
|---|---|
| DSpark drafter on 16 GB | 56.5 → 56.3 (Strata), 48.7 → 47.1–49.2 (maya-ik2), forced `IK2_DRAFT_ADAPT=0` identical; `timings.draft_n = 0` — the controller declines, and it is right |
| Two cards, layer split, all experts cached | 29.8–33.1 tok/s against 49 on one card |
| GGUF instead of a `.strata` pack | 29.5 vs 59.6 tok/s; GGUF never selects native kernels beyond 512/3072 experts (upstream #6729 is the same family of bug) |
| `--kv k8v4` / `k8v8` (4-bit / int8 KV) on HIP | upstream #6681: allocates more VRAM than fp16, OOMs earlier; `--kv fp8` only |
| `--kv-offload off` at 64 k | `alloc_gpu_buffer: out of memory` |
| `k8v4` inside maya-ik2 | not implemented (only `f16` / `fp8`; anything else is refused) |
| 100 k-token single request on Strata 0.2.20 | hit upstream #6755 (`kv grow` fatal) — this is what took the host down mid-session; stay ≤ ~64 k per request |
| UnbiasedStrata as a drop-in for Qwen | slower than 0.2.15 on both axes |
| Borrowing the RDNA4 WMMA path from Avalon/ggml for maya-ik2 | lead confirmed (`__builtin_amdgcn_wmma_f32_16x16x16_f16_w32_gfx12` takes the `mma.sync` fragment structs directly, `ggml-cuda/mma.cuh:1370`); my first integration compiled and ran but produced wrong values against the reference, so it was reverted — open item |

## 6. KV cache options, per engine

| Engine | Options | Cost per token | Verdict |
|---|---|---|---|
| maya-ik2 | `f16`, `fp8` (E4M3) | 32 KB / **16 KB** | **fp8** — 2.12 GiB at 131 k; FP16 costs 4.2 GiB (i.e. ~2 GiB of expert cache) and is not faster |
| strata-inkling | `fp16`, `fp8`, `k8v8` (`i8`/`q8`), `k8v4` | 32 / **16** / 16 / 12 KB | **fp8**; the integer modes are the broken-on-HIP path |
| strata (Qwen, 0.2.15) | `--kv int8`, `--kv-resident N` | — | **int8 + 20 480 resident cells**, as in production |

## 7. Verdict: what to run for what

| Use case | Engine | Model / file | Why |
|---|---|---|---|
| **Inkling, short or medium prompts (≤ 32 k)** | **`strata-inkling` (Strata 0.2.20)** | **`Inkling-2-Mini-SQ-10.strata`** | best prefill on the box (2 124–2 476 tok/s) and 48–60 tok/s decode |
| **Inkling, long context up to ~64 k** | **`strata-inkling` + `SQ-10`** | same | 37 tok/s at 62.7 k, 2.4× the SQ-15 pack |
| Inkling, single request beyond 64 k | `maya-ik2` (HIP port) | `UD-Q4_K_XL.gguf`, 131 k | Strata cannot survive #6755 there; maya held 131 k at 32.9 tok/s |
| Inkling, best quality per GiB | `strata-inkling` + `SQ-15` | 13.4 GiB pack | 50.5 tok/s short; only loses at depth because the KV leaves the card |
| **Qwen3.8-Flash-Next, all traffic** | **Strata 0.2.15 (unchanged)** | IQ3_S / IQ3_XXS + MTP | 70.9 / 76.8 tok/s; 0.2.20 is 10 % behind until its profile is regenerated |
| Agentic loops, tool calls | `maya-ik2` or `SQ-10` | — | maya keeps more speed under a growing conversation; SQ-10 wins if the prompt stays under ~32 k |

Rule of thumb on this card: **nothing with 14.7 GiB of experts is fast unless it also fits the
KV.** Every "slow" result in this document is the same failure — experts or KV crossing PCIe —
and every "fast" result is the same success: the pack small enough that both stay resident.

## 8. Reproduce

```sh
# Strata 0.2.20 engine for gfx1201
cd /media/timoti/Data/repos/Strata-0220/engine
cmake -S . -B build-hip -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON \
  -DCMAKE_HIP_ARCHITECTURES=gfx1201 -DSTRATA_HIP_ARCHS=gfx1201 \
  -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ -DCMAKE_PREFIX_PATH=/opt/rocm
cmake --build build-hip -j 12 --target strata strata-inkling

# Inkling on the SQ-10 pack, 120 k, FP8 KV
HIP_VISIBLE_DEVICES=1 LD_LIBRARY_PATH=/opt/rocm/lib build-hip/src/inkling2/strata-inkling \
  --bench --native /media/timoti/Storage/lmstudio/models/strata-engine/Inkling-2-Mini-Strata/Inkling-2-Mini-SQ-10.strata \
  --kv fp8 --cpu-threads 8 --prompt-len 1500 --gen 128

# maya-ik2 port
cd /media/timoti/Data/repos/maya-inkling-mini
cmake -S . -B build-hip -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON \
  -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_HIP_IK2_SPIKE=ON -DSTRATA_NATIVE_EXPERTS=ON \
  -DSTRATA_PREFILL_MMQ=ON -DSTRATA_BUILD_TESTS=OFF -DCMAKE_HIP_ARCHITECTURES=gfx1201 \
  -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ -DCMAKE_PREFIX_PATH=/opt/rocm
cmake --build build-hip -j 10 --target maya-ik2
```

llama-swap models added today (backups `config.yml.bak-*-2026-11-23`):
`inkling-2-mini-strata-sq10`, `inkling-2-mini-strata-sq15`, `inkling-2-mini-maya-hip`,
`qwen3.8-flash-IQ3_S-v0220`, `qwen3.8-flash-IQ3_XXS-v0220`.

## 9. Open items

1. **RDNA4 WMMA for maya-ik2** — the one lever left for it (prefill 924 → ~2 000, deep decode
   up); needs the fragment plumbing fixed and the FP64 kernel test as the gate.
2. **Regenerate the Qwen expert profile with 0.2.20 tooling** — the only thing standing between
   Qwen and the new engine.
3. **Upstream #6755** — Strata 0.2.20 dies around 71 k tokens in one request; until fixed, cap
   single requests at ~64 k there.
4. `strata-inkling --parallel` was never exercised: on SQ-10 there is VRAM for 2–4 slots, which
   would help an agent's parallel side calls.
