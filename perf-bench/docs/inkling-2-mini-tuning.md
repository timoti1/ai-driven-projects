# Inkling 2 Mini: engine selection, drafter and long-context tuning

All numbers were measured on `ryzen5800` (AMD Ryzen 7 5800 + 2x RX 9070 16 GB), model pinned to the
Gigabyte card (`0000:0b:00.0`, `HIP_VISIBLE_DEVICES=1` / `Vulkan1`). Greedy decoding unless stated,
code-shaped prompts, 128–256 generated tokens per sample, `timings` from the server as the source
of truth. Same protocol as `tests/spec-decode.json`.

## 1. Why the model was slow: not bandwidth, not FLOPs

`inkling2_loop` runs 24 physical layers, with the middle 12 executed three times → ~54–60 layer
passes per token, 8 of 128 experts per pass. Measurements:

| Check | Result | Conclusion |
|---|---|---|
| Dense 27B IQ3_XXS, same card | 33.7 tok/s | Inkling behaved like a *dense* 26B — no MoE payoff |
| Dense 7B Q4_K_M | 98.7 tok/s = 434 GB/s | card reaches 68% of 640 GB/s peak |
| Inkling IQ3_XXS | 33.4 tok/s | ~13% of bandwidth, ~0.5% of compute peak |

The upstream fork notes confirm the mechanism: **~7 650 kernel launches per token**. Small ops of a
few microseconds each, thousands of them per token — the GPU idles between them (launch latency).

Rejected along the way (all measured): `--poll 1`, `--prio 3`, `-t 1` (no effect), disabling HIP
graphs (−12%), F16 or q8_0 KV (no speed effect at all), ngram speculation (`ngram-simple`,
`ngram-map-k`, `ngram-mod`: no gain; `ngram-cache`: −30%), dual-GPU layer split (9.8 tok/s — the x2
slot destroys it), smaller/bigger quants of other layouts (`inkling2` 48-block files are a different
architecture revision that mainline cannot load).

## 2. Engine matrix

| Engine | tg, code | Notes |
|---|---|---|
| mainline llama.cpp (b12600-ish), no drafter | 33.4 | baseline |
| mainline + `dspark` drafter | will not load | drafter was built for a newer loader: padded markov vocab, missing `markov_w2`, 5120-wide `joint_proj`, no `fc` |
| Unsloth prebuilt `b12588-mix` + drafter | 45–54 | drafter works, but 15.5 GB VRAM and slower base |
| `GodGMN/llama.cpp@inkling-rdna3` (HIP fusions) | 56.6 | 7 650 → ~3 000 kernels/token; `GGML_INK_NO_FUSE=1` drops it to 37.0 |
| **same fork + PR #32218 (DSpark) cherry-picked** | **60.9–70.9** | final engine; branch `fusion-dspark`, built for `gfx1201` |

The mmvq retune in that branch is RDNA3-only and does not apply to RDNA4; the win on RX 9070 comes
from the fused small ops, the in-kernel relative-position bias for Flash Attention and the q8_1
input cache. Correctness checked on generated code; the branch author reports wikitext-2 PPL
unchanged (5.9465 → 5.9472).

## 3. Drafter vs context depth

The drafter (0.4 GB, converted from the model's own `mtp.safetensors`, block size 8) helps only
while the verify batch is cheap:

| Prompt depth | Without drafter | With drafter (n-max 6) | Draft acceptance |
|---|---|---|---|
| ~75 (empty) | 56.7 | **65.9** | 45% |
| ~6 000 | **55.1** | 42.7 | 24% |
| ~24 000 | **52.8** | 43.3 | 27% |
| ~47 000 | **50.8** | 38.9 | 26% |
| ~71 000 | **48.8** | 43.8 | 35% |
| ~93 000 | **46.8** | 39.0 | 32% |

Each draft step pushes n+1 tokens through the whole model *with attention over the full context*, so
the verify cost grows with depth while accepted tokens per step stays at 25–45%. Above ~10k the
drafter is a net loss. On free-form prose acceptance falls to 28–34% even at depth 0, so it is only
worth enabling for code-like output at short context. `n-max` sweep (code, depth 0): 2 → 48.8,
3 → 51.6, 4 → 53.6, 5 → 51.0, 6 → 55.8, 7 → 60.5 with acceptance collapsing 78% → 38%.

## 4. Parallel sessions

`--parallel N` splits `--ctx-size` across N slots; aggregate throughput is what matters for agents.

| Sessions | No drafter: per session | No drafter: aggregate | With drafter: per session | With drafter: aggregate |
|---|---|---|---|---|
| 1 | 55.3 | 55.7 | — | — |
| 2 | 39.6–40.4 | **79.8** | 24.6–24.8 | 49.6 |
| 4 | 22.6–30.3 | **91.2** | 13.4–16.0 | 54.2 |
| 8 | 9.1–20.4 | 73.7 | 6.6–11.4 | 53.2 |

Measured through llama-swap with 4 concurrent requests: 30.9–31.7 tok/s per session, **124.7 tok/s
aggregate**. The drafter is a clear loss under parallel load (batching mixes slots, acceptance drops
to 26–29%), so multi-session profiles run without it. Four sessions is the knee; eight saturates.

## 5. Context budget (4-bit KV)

KV cache cost measured from VRAM deltas: **~19.8 KiB of VRAM per context token** with `q4_0` K/V
(≈12.7 KiB of pure cache + per-slot overhead). KV quantisation has **no** effect on speed
(q4_0 56.7 / q8_0 56.8 / f16 56.7 at depth 0), only on memory and recall — hence `q8_0` where it
fits and `q4_0` only for the largest profiles.

Search for the largest `--parallel 2` context on a 15.9 GiB card, target 300–400 MiB left free:

| `--ctx-size` | per session | VRAM used | free |
|---|---|---|---|
| 131 072 | 65 536 | 14 091 MiB | 2 213 MiB |
| 163 840 | 81 920 | 14 722 MiB | 1 582 MiB |
| 196 608 | 98 304 | 15 354 MiB | 950 MiB |
| 212 992 | 106 496 | 15 670 MiB | 634 MiB |
| 225 280 | 112 640 | 15 908 MiB | **396 MiB** |
| 226 304 | 113 152 | 15 928 MiB | 376 MiB |
| 227 328 | 113 664 | 15 948 MiB | 356 MiB |

Selected profile: `--parallel 2 --ctx-size 225280` (2 × 110k), `q4_0` K/V, `-ub 256`, no drafter →
**41.7 tok/s per session, 84 tok/s aggregate, 394 MiB free**.

## 6. Final profiles

| Profile | Sessions × ctx | Speed | KV | Use |
|---|---|---|---|---|
| `inkling-2-mini-iq3xxs` | 1 × 96k | 66 empty / 47 at 93k | q8_0 | single stream, short-to-medium context, code |
| `inkling-2-mini-long` | 1 × 128k | 66 empty / 47 at 93k | q4_0 | one very long document |
| `inkling-2-mini-multi` | 4 × 32k | 31/session, ~125 aggregate | q8_0 | several agents at once (default) |
| `inkling-2-mini-multi2` | 2 × 110k | 42/session, ~84 aggregate | q4_0 | two agents with large contexts |

Engine for all four: `llama-server` from `/home/timoti/llama-rdna3`, branch `fusion-dspark`
(`inkling-rdna3` + PR #32218), built with `-DGGML_HIP=ON -DCMAKE_HIP_ARCHITECTURES=gfx1201`,
`LD_LIBRARY_PATH=/opt/rocm/lib`, `HSA_OVERRIDE_GFX_VERSION=12.0.1`, flags `-fa on -ub 256
--parallel N --ctx-size X --cache-ram 0`.

## 7. CPU

`build-cpu` of mainline llama.cpp, no drafter: the model does not produce a first answer within
**11.5 minutes** (log: task cancelled after 11 m 40 s), so CPU-only inference is not viable on this
8-core AVX2 machine (Ryzen 7 5800 has no AVX-512/BF16). The fast CPU engine already installed,
`ik_llama.cpp` (`build 656036d9`), has **zero** `inkling2` symbols, so it cannot load the model: the
looped architecture would have to be ported into it (model file + graph + arch tables ≈ 1k+ lines),
which is a project of its own rather than a flag. Practical alternative on this box: keep the model
on one GPU and use the parallel-session profiles above.

## 8. Reproduce

```bash
# engine
git clone -b inkling-rdna3 https://github.com/GodGMN/llama.cpp llama-rdna3
cd llama-rdna3 && git fetch https://github.com/ggml-org/llama.cpp refs/pull/32218/head:pr32218
git checkout -B fusion-dspark && git cherry-pick pr32218
cmake -B build-hip -DGGML_HIP=ON -DCMAKE_HIP_ARCHITECTURES=gfx1201 -DCMAKE_BUILD_TYPE=Release
cmake --build build-hip --target llama-server -j16

# single stream with drafter
LD_LIBRARY_PATH=/opt/rocm/lib HIP_VISIBLE_DEVICES=1 HSA_OVERRIDE_GFX_VERSION=12.0.1 \
  build-hip/bin/llama-server -m Mainline_Support/Inkling-2-Mini-UD-IQ3_XXS.gguf \
  -md dspark-Inkling-2-Mini-Q8_0.gguf --spec-type draft-dspark --spec-draft-n-max 6 -ngld 99 \
  --device ROCm0 -ngl 99 -fa on -ctk q4_0 -ctv q4_0 -ub 256 -c 131072 --jinja
```
