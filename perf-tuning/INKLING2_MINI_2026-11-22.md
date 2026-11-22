# Inkling 2 Mini: engine selection, drafter, long context and the two-card router

Investigated 2026-11-21/22 on the two-GPU host. Model pinned to the **Sapphire** card
(`0000:06:00.0`, `HIP_VISIBLE_DEVICES=0`) after the Gigabyte slot was freed for heavy
workloads. Companion tooling: [`../perf-bench`](../perf-bench). Related:
[BUILD_PROVENANCE.md](BUILD_PROVENANCE.md), [MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md),
[VULKAN_SAPPHIRE_2026-11-04.md](VULKAN_SAPPHIRE_2026-11-04.md),
[QWEN38_27B_RDNA_BOOSTS_2026-11-22.md](QWEN38_27B_RDNA_BOOSTS_2026-11-22.md).

**TL;DR**

- The model was **launch-latency bound, not bandwidth bound**: ~7 650 kernel launches per
  token (54–60 layer passes × 8-of-128 experts). Card reached 434 GB/s on a 7B control
  test, while Inkling moved ~13% of that.
- A third-party HIP-fusion fork (**`GodGMN/llama.cpp@inkling-rdna3`**) plus cherry-picked
  **PR #32218** (DSpark) took single-stream decode from **33 → 57 tok/s without drafter**
  and **66 → 71 tok/s with drafter**; `GGML_INK_NO_FUSE=1` proves the fusions are the win
  (56.6 → 37.0).
- The drafter helps **only under ~10k context** and **never under parallel load**;
  multi-session profiles therefore run without it.
- Final profile lives on Sapphire: **2 sessions × 100 352 ctx, KV q4_0, 364 MiB VRAM
  left free, 37–38 tok/s per session, ~75 tok/s aggregate**.
- Router rule verified live: models on the **same** card evict each other, models on
  **different** cards coexist.

## 1. Diagnosis

| Check | Result | Conclusion |
|---|---|---|
| Dense 27B IQ3_XXS, same card | 33.7 tok/s | Inkling behaved like a dense 26B — no MoE payoff |
| Dense 7B Q4_K_M | 98.7 tok/s = 434 GB/s (68% of peak) | memory subsystem is fine |
| Inkling IQ3_XXS | 33.4 tok/s | ~13% bandwidth, ~0.5% compute peak |

Rejected by measurement: `--poll 1`, `--prio 3`, `-t 1` (no effect), HIP graphs off (−12%),
F16/q8_0 KV (no speed effect), ngram speculation (no gain; `ngram-cache` −30%), dual-GPU
layer split (9.8 tok/s — the chipset slot destroys it), 48-block `inkling2` GGUFs (different
architecture revision, mainline cannot load them).

## 2. Engine matrix (code prompts, greedy)

| Engine | tg | Notes |
|---|---|---|
| mainline llama.cpp, no drafter | 33.4 | baseline |
| mainline + `dspark` drafter | will not load | drafter built for a newer loader (padded markov vocab, no `markov_w2`, 5120-wide `joint_proj`, no `fc`) |
| Unsloth prebuilt `b12588-mix` + drafter | 45–54 | drafter works; 15.5 GB VRAM, slower base |
| `inkling-rdna3` fork (HIP fusions) | 56.6 | 7 650 → ~3 000 kernels/token |
| **fork + PR #32218 (DSpark)** | **60.9–70.9** | final engine, branch `fusion-dspark`, `gfx1201` |

The fork's mmvq retune is RDNA3-only and does not apply to RDNA4; on RX 9070 the win comes
from fused small ops, in-kernel relative-position bias for Flash Attention and the q8_1
input cache.

## 3. Drafter vs context depth (fork build, IQ3_XXS)

| Prompt depth | No drafter | Drafter n-max 6 | Acceptance |
|---|---|---|---|
| ~75 (empty) | 56.7 | **65.9** | 45% |
| ~6 000 | **55.1** | 42.7 | 24% |
| ~24 000 | **52.8** | 43.3 | 27% |
| ~47 000 | **50.8** | 38.9 | 26% |
| ~71 000 | **48.8** | 43.8 | 35% |
| ~93 000 | **46.8** | 39.0 | 32% |

Each draft step pushes n+1 tokens through the model with attention over the full context:
verify cost grows with depth while accepted tokens per step stays at 25–45%. On prose,
acceptance is 28–34% even at depth 0. `n-max` sweep at depth 0: 2 → 48.8, 3 → 51.6,
4 → 53.6, 5 → 51.0, 6 → 55.8, 7 → 60.5 with acceptance collapsing 78% → 38%.

## 4. Parallel sessions (no drafter vs drafter)

| Sessions | No drafter per session | No drafter aggregate | Drafter per session | Drafter aggregate |
|---|---|---|---|---|
| 1 | 55.3 | 55.7 | — | — |
| 2 | 39.6–40.4 | **79.8** | 24.6–24.8 | 49.6 |
| 4 | 22.6–30.3 | **91.2** | 13.4–16.0 | 54.2 |
| 8 | 9.1–20.4 | 73.7 | 6.6–11.4 | 53.2 |

Through llama-swap with 4 concurrent requests: 30.9–31.7 tok/s per session, **124.7 tok/s
aggregate**. Batched verification mixes slots, acceptance falls to 26–29%, so multi-session
profiles run without a drafter. Four sessions is the knee.

## 5. Context budget on Sapphire (KV q4_0)

Cost measured from VRAM deltas: **~19.8 KiB of VRAM per context token** with q4_0 K/V.
KV quantisation does not change speed (q4_0 56.7 / q8_0 56.8 / f16 56.7 at depth 0).

Search for the largest `--parallel 2` context leaving 300–400 MiB free:

| `--ctx-size` | per session | VRAM used | free |
|---|---|---|---|
| 196 608 | 98 304 | 15 860 MiB | 444 MiB |
| **200 704** | **100 352** | **15 940 MiB** | **364 MiB** |
| 202 752 | 101 376 | 15 980 MiB | 324 MiB |
| 212 992 | 106 496 | 16 176 MiB | 128 MiB |

Selected: **200 704 (2 × 100 352)**, 364 MiB free. Measured on Sapphire: 37.2–38.4 tok/s
per session, 74.9 tok/s aggregate (the Gigabyte card did 41.7 / 84 on the same shape — the
chipset slot costs ~10%).

## 6. Card placement and router rule

Only one Inkling profile remains, on the Sapphire card:
`inkling-2-mini-iq3xxs-C2` (`-C2` = two parallel sessions, matching the existing naming in
the config). The four Gigabyte profiles were removed so the fast x16 card stays free for
heavy single-stream work.

Matrix groups by card, and the `pair` set gives exactly the required semantics:

```
pair: (tiel|iq3xxs|iq3xxsrocm|flashS|flashX|avalon|avalon2|daisyrose)      # Gigabyte
    & (iq3xxsrocms|iq3xxspilora|iq3xxsnvdraft|daisyroseS|inklingC2)       # Sapphire
```

Verified live through the API:

| Step | Running set afterwards | VRAM G / S |
|---|---|---|
| request `inkling-2-mini-iq3xxs-C2` | inkling | 0.1 / 15.6 GiB |
| request `daisyrose-…-ROCm` (other card) | daisyrose + **inkling kept** | 14.9 / 15.6 GiB |
| request `daisyrose-…-Sapphire` (same card) | daisyrose + daisyroseS (**inkling evicted**) | 14.9 / 15.1 GiB |
| request `tiel-coder-35b-a3b` (same card) | daisyroseS + tiel (**daisyrose evicted**) | 11.8 / 15.1 GiB |

## 7. CPU

Mainline `build-cpu`, no drafter: no first answer within **11 m 40 s** (task cancelled), so
CPU-only inference is not viable here (Ryzen 7 5800, 8 cores, AVX2 only — no AVX-512/BF16).
The fast CPU engine already installed, `ik_llama.cpp` (`656036d9`), contains **zero**
`inkling2` symbols and cannot load the model; the looped architecture would have to be
ported (model + graph + arch tables, ~1k+ lines) — a separate project, not a flag.

## 8. Reproduce

```bash
git clone -b inkling-rdna3 https://github.com/GodGMN/llama.cpp llama-rdna3
cd llama-rdna3
git fetch https://github.com/ggml-org/llama.cpp refs/pull/32218/head:pr32218
git checkout -B fusion-dspark && git cherry-pick pr32218
cmake -B build-hip -DGGML_HIP=ON -DCMAKE_HIP_ARCHITECTURES=gfx1201 -DCMAKE_BUILD_TYPE=Release
cmake --build build-hip --target llama-server -j16

# two sessions on the Sapphire card, largest context with 364 MiB free
LD_LIBRARY_PATH=/opt/rocm/lib HIP_VISIBLE_DEVICES=0 HSA_OVERRIDE_GFX_VERSION=12.0.1 \
  build-hip/bin/llama-server -m Mainline_Support/Inkling-2-Mini-UD-IQ3_XXS.gguf \
  --device ROCm0 -ngl 99 -fa on --parallel 2 -ub 256 -c 200704 \
  -ctk q4_0 -ctv q4_0 --jinja --cache-ram 0
```
