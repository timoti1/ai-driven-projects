# Inkling 2 Mini and Qwen3.8-Flash-Next on AMD RDNA4: five engines, one card

Investigated 2026-11-23 on the two-GPU host, all measurements on the **Gigabyte RX 9070**
(`0000:0b:00.0`, `HIP_VISIBLE_DEVICES=1`, PCIe 4.0 x16, 15.9 GiB usable). The question came
from an Unbiased Bob video recommending `maya-ik2` + Unsloth `UD-Q4_K_XL` for Inkling 2 Mini,
with "not llama.cpp" as the headline. Companion tooling: [`../perf-bench`](../perf-bench).
Related: [INKLING2_MINI_2026-11-22.md](INKLING2_MINI_2026-11-22.md) (the same model on the
Sapphire card and the two-card router), [STRATA_OPTIMIZATION.md](STRATA_OPTIMIZATION.md),
[AVALON_OPTIMIZATION_COMPARISON.md](AVALON_OPTIMIZATION_COMPARISON.md).

## TL;DR

- **`strata-inkling` (Strata 0.2.20) owns this card at every depth, on every metric.** With its
  pack and `--draft off`: **SQ-15 = 70.4–73.5 tok/s** short, 64.8 after a 2 k prompt,
  **39.7 tok/s at a 62 756-token prompt** (1 406 tok/s prefill); SQ-10 = 59.6–72, 36–37 at 62.7 k
  with the best prefill on the box (2 476). `maya-ik2`, the CUDA engine ported to HIP below,
  manages 49 / 32.9 / 924 — and has been removed from the host.
- **`maya-ik2` did run on this AMD card — I ported it** (it ships CUDA-only), and the port is
  correct (its own FP64 kernel reference suite passes). At 16 GB it loses to the Strata pack
  build on every axis, so the entry, its config and its build were deleted at the end of the
  session; the port notes are kept as §10.
- **The GGUF is the slow path for `strata-inkling`.** With `UD-Q4_K_XL` the engine reports
  *"native lossless GGUF_RAW GPU kernels active for 512/3072 experts"* and manages 29.5 tok/s.
  The `.strata` packs are the intended format, and the pack size is what decides speed:
  **SQ-10 (9.75 GiB) > SQ-15 (13.4 GiB) > SQ-20 (needs 24 GiB)**.
- **The DSpark drafter costs speed on this card, in every engine, and is now disabled**: on
  Strata, `--draft off` gives **+9 % decode on SQ-10 (60.1 → 65.7) and +15 % decode / +29 %
  prefill on SQ-15 (56.8 → 65.2, 2 080 → 2 687)**; through llama-swap it is 70.4–73.5 tok/s
  against 50.5 with the drafter. On maya-ik2 it is 48.7 → 47.1–49.2 and forcing it
  (`IK2_DRAFT_ADAPT=0`) changes nothing. Acceptance on SQ packs is only ~13–22 %.
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
- **On quality the picture is different from speed (§11)**: with the same harness Hy4-Flash SQ-64
  on two cards and thinking high scores **93.6 %**, Inkling SQ-15 **80.2 %**, SQ-10 **72.7 %** —
  Hy4 wins 9 of 10 benches, Inkling wins only on prefill (2 300 vs 290 tok/s) and short-prompt
  decode (70 vs 40 tok/s).
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

The port notes are kept as a separate file after the engine was deleted:
[MAYA_IK2_HIP_PORT_2026-11-23.md](MAYA_IK2_HIP_PORT_2026-11-23.md).

## 3. Inkling 2 Mini: the full matrix

All rows: Gigabyte card, `--kv fp8` where the engine allows it, single stream, temperature 1.0,
`reasoning_effort none`. "CLI" rows are the engine's own `--bench` (no 120 k reservation);
"server" rows run through llama-swap with the KV reserved for 120 k — that reservation is what
makes the difference between the two columns, not the engine.

| Engine / file | ctx | 1.5–2 k prompt | 32 k | 62.7 k |
|---|---|---:|---:|---:|
| **`strata-inkling` + `SQ-10` pack, CLI** | — | **59.6 tok/s · 2 476 pp** | **29.2 · 1 758** | 18.4 · 1 387 |
| **`strata-inkling` + `SQ-10` pack, server** | **120 k** | **47–48 · 2 124** | — | **37.0 · 1 341** |
| **`strata-inkling` + `SQ-15` pack, CLI, `--draft off`** | — | **65.2 · 2 687** | — | — |
| **`strata-inkling` + `SQ-15` pack, server, `--draft off`** | **120 k** | **70.4–73.5 · 2 312** | — | **39.7 · 1 406** |
| `strata-inkling` + `SQ-15`, same as above but with the drafter | 120 k | 50.5 · 1 651 | 21.3 · 1 439 | 15.3 · 1 016 |
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
| DSpark drafter on 16 GB | Strata, CLI 1.5 k prompt: SQ-10 60.1 → **65.7** and SQ-15 56.8 → **65.2** tok/s with `--draft off`, SQ-15 prefill 2 080 → **2 687**; through llama-swap SQ-15 goes 50.5 → 70.4–73.5 tok/s. maya-ik2: 48.7 → 47.1–49.2, `IK2_DRAFT_ADAPT=0` identical, `timings.draft_n = 0`. Both configs now ship `--draft off` |
| Two cards, layer split, all experts cached | 29.8–33.1 tok/s against 49 on one card |
| GGUF instead of a `.strata` pack | 29.5 vs 59.6 tok/s; GGUF never selects native kernels beyond 512/3072 experts (upstream #6729 is the same family of bug) |
| `--kv k8v4` / `k8v8` (4-bit / int8 KV) on HIP | upstream #6681: allocates more VRAM than fp16, OOMs earlier; `--kv fp8` only |
| `--kv-offload off` at 64 k | `alloc_gpu_buffer: out of memory` |
| `k8v4` inside maya-ik2 | not implemented (only `f16` / `fp8`; anything else is refused) |
| 100 k-token single request on Strata 0.2.20 | hit upstream #6755 (`kv grow` fatal) — this is what took the host down mid-session; stay ≤ ~64 k per request |
| UnbiasedStrata as a drop-in for Qwen | slower than 0.2.15 on both axes |
| Borrowing the RDNA4 WMMA path from Avalon/ggml for maya-ik2 | lead confirmed (`__builtin_amdgcn_wmma_f32_16x16x16_f16_w32_gfx12` takes the `mma.sync` fragment structs directly, `ggml-cuda/mma.cuh:1370`); my first integration compiled and ran but produced wrong values against the reference, so it was reverted — open item |

## 5b. The drafter, and why it is off

Both `strata-inkling` and `maya-ik2` speculate with **DSpark**, Thinking Machines' own drafter
(ships with the checkpoint; embedded in every `.strata` pack — the Strata server appends
`--draft dspark` by itself, an external one can be named with `--dspark mtp.safetensors`).
Its state is 2 sliding-window-1025 KV rings + 1 global KV + an f_rnn ring; it drafts **up to 7
tokens per step** (`0..max_draft, typically up to 7`) and one verify pass emits 1 to 8, and
Strata only speculates while exactly one request is active and its prefill is done.

Measured acceptance on this card (serve `timings`, 200–300-token generations):

| Pack | drafted / accepted per request | acceptance | HF's own "AR alpha" |
|---|---|---:|---:|
| SQ-10 | 90/13, 94/17, 43/6, 40/4 | **13–18 %** | 2.701 |
| SQ-15 | 221/34, 99/14, 64/14, 62/9 | **13–22 %** | 2.583 |

That is the whole story: at ~15 % acceptance a 5-token window pays for itself only when the
verify pass is nearly free — on a 24 GB card. Here every miss goes to host memory, so the
drafter is a net loss and both configs now carry `--draft off`.

## 5c. Thinking level: 0.5 everywhere (low-to-middle)

Inkling 2 Mini's template carries the model card's own scale —
`none 0.0 · minimal 0.1 · low 0.2 · medium 0.7 · high 0.9 · xhigh/max 0.99` — and writes it into
the prompt as `Thinking effort level: N`. **Both engines now run at 0.5** when a request names
nothing, which is neither the 0.7 ("medium") that the video warns about nor the 0.0 that Strata
forced:

| Model | Before | Now | How |
|---|---|---|---|
| `inkling-2-mini-strata-sq10` / `-sq15` | **forced 0.0** — `inkling_dialect.normalize_effort()` returned `"none"` for every value ("Inkling-2-Mini has no thinking mode") | **0.5** | patch to `terminal/serve/inkling_dialect.py`: `DEFAULT_EFFORT = 0.5`, numeric pass-through in `normalize_effort`/`template_kwargs` (backup `.bak-050`) |
| `inkling-2-mini-maya-hip` | **0.9** — no config value, so the template default applied | **0.5** | `"reasoning_effort": 0.5` in `ik2-solo.json` **plus** three patches: `frontend.config_effort` (a number is accepted, it refused "not a number"), `frontend.effort_kwargs` (passes it through), and the Inkling branch of `ChatTemplate.render` (dropped anything not in `INKLING_EFFORT`, so a float silently became 0.9) |

Verified by rendering the prompt directly: `Thinking effort level: 0.5` on both. A client can
still override per request — `reasoning_effort: "none" | "minimal" | "low" | "medium" | "high"`
or a number `0.0–0.99`; Anthropic's `thinking.budget_tokens` is mapped to a level
(< 2 k → low, < 8 k → medium, else high).

Observed effect: at 0.9 maya spent 402 characters reasoning about a trivial counting question;
at 0.5 the same class of question answers directly, and a three-step arithmetic prompt produced
557 characters of reasoning plus a 275-character answer at **49.1 tok/s** (375 tokens, 10 s).
One run crashed the maya port (`exit code -11`) right after the patch, and the retry on the same
prompt was clean — an instability of the HIP port to keep an eye on, not of the Strata engine.

## 6. KV cache options, per engine

| Engine | Options | Cost per token | Verdict |
|---|---|---|---|
| maya-ik2 | `f16`, `fp8` (E4M3) | 32 KB / **16 KB** | **fp8** — 2.12 GiB at 131 k; FP16 costs 4.2 GiB (i.e. ~2 GiB of expert cache) and is not faster |
| strata-inkling | `fp16`, `fp8`, `k8v8` (`i8`/`q8`), `k8v4` | 32 / **16** / 16 / 12 KB | **fp8**; the integer modes are the broken-on-HIP path |
| strata (Qwen, 0.2.15) | `--kv int8`, `--kv-resident N` | — | **int8 + 20 480 resident cells**, as in production |

## 7. Verdict: what to run for what

| Use case | Engine | Model / file | Why |
|---|---|---|---|
| **Inkling, anything ≤ 32 k prompts** | **`strata-inkling` (0.2.20)** | **`SQ-15.strata`** (13.4 GiB, 4.35 bpw ≈ IQ4_XS) | **70.4–73.5 tok/s** decode, 2 312 prefill — the fastest and the best quality that runs here (top-1 96.7 %) |
| **Inkling, long prompts (32–64 k)** | **`strata-inkling`** | **`SQ-15`**, or `SQ-10` if VRAM is tight | SQ-15 **39.7 tok/s** at 62.7 k with `--draft off`; SQ-10 37.0 with 3.6 GiB more headroom |
| Inkling, maximum prefill | `strata-inkling` | `SQ-10` | 2 476 tok/s at 1.5 k — fastest prompt reading measured, at 3.17 bpw |
| Inkling, best fidelity | `strata-inkling` | `SQ-20` | bit-exact (KLD 0.00000) but 18.0 GiB — **does not fit** this card |
| Inkling, single request > 64 k | *nothing here* | — | Strata dies at ~71 k (upstream #6755); `maya-ik2` was the only one that held 131 k, and it is gone |
| **Qwen3.8-Flash-Next, all traffic** | **Strata 0.2.15** | IQ3_S / IQ3_XXS + MTP | 70.9 / 93.8 tok/s; 0.2.20 is ~10 % behind until its profile is regenerated |

Rule of thumb on this card: **the pack size decides everything, and the drafter must be off.**
SQ-10 vs SQ-15 is a trade of 3.6 GiB against ~8 points of top-1 agreement; with `--draft off`
SQ-15 no longer collapses at depth, so it is the default and SQ-10 is the "give me VRAM back"
option. Everything that was slow in this document was experts or KV crossing PCIe.

`maya-ik2` (the HIP port, §2/§10) is retired: 49 tok/s short, 32.9 at 62.7 k, prefill 924, and
one SIGSEGV observed under a longer thinking trace. Removed from llama-swap and deleted from
`/media/timoti/Data/repos/maya-inkling-mini`; the 17.6 GB `UD-Q4_K_XL.gguf` (its only consumer,
5.34 bpw, the highest-fidelity file on the box) was left on disk in case it is wanted again.

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

1. **Upstream #6755** — Strata 0.2.20 dies around 71 k tokens in one request (it took this host
   down once); until fixed, cap single requests at ~64 k. With maya-ik2 gone there is no engine
   on this machine for a single 100 k+ request.
2. **Regenerate the Qwen expert profile with 0.2.20 tooling** — the only thing standing between
   Qwen and the new engine.
3. `strata-inkling --parallel` was never exercised: on SQ-10 there is VRAM for 2–4 slots, which
   would help an agent's parallel side calls.
4. Re-measure the SQ packs at 1.5 k / 32 k / 64 k **once upstream fixes the drafter's cost** —
   the whole depth story changed the moment `--draft off` was applied, so the shipped defaults
   are worth re-checking after each release.

## 10. Appendix: what `SQ-10` / `SQ-15` / `SQ-20` are, in llama.cpp terms

The pack name is **its size in GB, not a quantization scheme** ("The number in a pack's name is
its approximate size in GB, not the card it needs", HF card). Inkling 2 Mini is 26.4 B
parameters, so bits per weight fall out of the file sizes:

| Deliverable | Size | bpw | Closest llama.cpp recipe | Their own quality vs the original |
|---|---:|---:|---|---|
| `UD-IQ2_XXS.gguf` (Unsloth) | 8.49 GB | 2.57 | IQ2_XXS | — |
| `UD-Q2_K_XL.gguf` | 9.14 GB | 2.77 | Q2_K | — |
| **`SQ-10.strata`** | **10.47 GB** | **3.17** | **IQ3_XXS–IQ3_S** | KLD 0.0502 · WT2 PPL 6.461 (+0.320) · top-1 **92.35 %** |
| `UD-IQ3_XXS.gguf` | 11.66 GB | 3.53 | IQ3_S | — |
| `UD-Q3_K_XL.gguf` | 13.63 GB | 4.13 | Q3_K_L | — |
| **`SQ-15.strata`** | **14.35 GB** | **4.35** | **IQ4_XS / Q4_K_S** | KLD 0.00889 · PPL 6.177 (+0.036) · top-1 **96.68 %** |
| `UD-Q4_K_XL.gguf` | 17.63 GB | 5.34 | Q4_K_M+ (dynamic, dense at Q8) | — |
| **`SQ-20.strata`** | **19.35 GB** | **5.86** | Q5_K_M / Q6_K — but **lossless** | KLD 0.00000 · PPL 6.141 · top-1 **100 %** |

The last row explains the oddity: SQ-20 is not "a 6-bit quant", it is **the original NVFP4
checkpoint repacked**, so it is bit-exact (KLD 0.00000) — the weights were never re-quantized,
which is why `strata-inkling` can run them "lossless direct GGUF_RAW".

Consequence for the choice in §3: **SQ-10 buys its 37 tok/s at 62 k with 7.65 points of top-1
agreement and +0.32 WikiText-2 perplexity**. If that matters for a task, `SQ-15` is a 4-bit
class pack for ~1 % top-1 — the cost is only the depth collapse (15.3 tok/s at 62 k) and 3.6 GiB
of VRAM. `UD-Q4_K_XL` (5.34 bpw) is between the two on size but is only usable through
`maya-ik2` on this card.

## 11. Quality: the benchmark suite (2026-11-23/24)

The same harness as always (`../quality-bench`): ten benches, one fresh Docker container per
bench, driven by a `pi` agent that must call tools (`_show_batch.py`, `_append_batch.py`,
`solutions.py`, `out.txt`) and is scored afterwards by `score.py`. Every model below ran the
identical prompts, 200 MMLU / 100 GSM8K / 200 ARC / 200 HellaSwag / 100 MATH / 200 WinoGrande /
100 BBH / 30 HumanEval / 50 Terminal / 50 TerminalHard = 1230 scored items.

| Bench | **Hy4-Flash SQ-64** (220B-A12B, 2 GPUs, thinking high) | **Inkling SQ-15** (4.35 bpw) | **Inkling SQ-10** (3.17 bpw) |
|---|---:|---:|---:|
| MMLU | **182/200 = 91.0 %** | 162/200 = 81.0 % | 157/200 = 78.5 % |
| GSM8K | **97/100 = 97.0 %** | 58/100 = 58.0 % | 36/100 = 36.0 % |
| HellaSwag | **185/200 = 92.5 %** | 175/200 = 87.5 % | 167/200 = 83.5 % |
| ARC-Challenge | **198/200 = 99.0 %** | 191/200 = 95.5 % | 185/200 = 92.5 % |
| MATH | **68/100 = 68.0 %** | 39/100 = 39.0 % | 9/100 = 9.0 % |
| WinoGrande | **192/200 = 96.0 %** | 167/200 = 83.5 % | 152/200 = 76.0 % |
| BBH | **100/100 = 100 %** | 69/100 = 69.0 % | 100/100 = 100 % |
| HumanEval | 29/30 = 96.7 % | 29/30 = 96.7 % | 0/30 = 0 % |
| Terminal (agent) | **50/50 = 100 %** | 48/50 = 96.0 % | 39/50 = 78.0 % |
| TerminalHard (agent) | **50/50 = 100 %** | 49/50 = 98.0 % | 49/50 = 98.0 % |
| **OVERALL** | **1151/1230 = 93.6 %** | **987/1230 = 80.2 %** | **894/1230 = 72.7 %** |
| Wall clock for the run | 4 h 05 min | 1 h 00 min | 55 min |

### The same workload as a speed test

The suite is a real agentic load (4–28 K-token prompts, tool calls, long answers), so the
engine's own counters give a better picture than any idle benchmark:

| Configuration | prefill | decode | experts in VRAM | host RAM |
|---|---:|---:|---:|---:|
| Hy4-Flash SQ-64, **1 GPU**, thinking none | 245 tok/s | 15.6 tok/s | 8.9 GB | 52.9 GB |
| **Hy4-Flash SQ-64, 2 GPUs (layer split), thinking none** | **290 tok/s** | **40.6 tok/s** | **22 GiB** | 36.8 GB |
| Hy4-Flash SQ-64, 2 GPUs, **thinking high** (the scored run) | 290 tok/s | ~33 tok/s | 22 GiB | 36.8 GB |
| Inkling SQ-15, 1 GPU, no drafter | 2 312 tok/s | 70 tok/s (1 K prompt) · 39.7 (62.7 K) | 13.4 GiB pack | — |

Prompt-cache reuse over the Hy4 runs: 79 % of prompt tokens served from the conversation cache,
which is what keeps a 290 tok/s prefill from dominating the wall clock.

### What the numbers say

- **Hy4-Flash wins on quality, and by a distance**: +13.4 points over the best Inkling pack, and
  it wins 9 of 10 benches (HumanEval is a tie at 96.7 %). A 220B-A12B model at SQ-64 is simply in
  another class than a 26B model at 4.35 bpw.
- **Where Inkling still wins is start-up speed**: 2 300 tok/s prefill vs 290, and 70 tok/s decode
  on short prompts. For a chat turn or a small edit, Inkling SQ-15 feels faster; for anything that
  scores quality, Hy4 wins outright.
- **The two-card layer split was the biggest win of the session**: decode 15.6 → 40.6 tok/s
  (+160 %) and prefill 245 → 290, entirely because 22 GiB of experts moved into VRAM (both cards
  at 14.4/15.9 GB) instead of being computed by the CPU. The chipset x2 link costs nothing —
  activations crossing it are 6 KB per token. Filling the last gigabyte per card does not help
  (probes at 20/22/24 GiB: 29.2 / 29.0 / 28.2 tok/s).
- **Thinking level matters more than quantisation level**: Inkling SQ-10 (3.17 bpw, thinking off)
  scored 72.7 %, SQ-15 (4.35 bpw, thinking off) 80.2 %, Hy4 SQ-64 with thinking high 93.6 %.
  MATH is the clearest case: 9 % → 39 % → 68 %.
- **An earlier Inkling SQ-10 run scored 40.1 %** and is *not* comparable: the model was being
  reloaded under it during the measurements (MMLU died after two tool calls, HumanEval never
  created `solutions.py`). It is kept here as the example of why runs must not be disturbed.

### Harness fixes without which these numbers are meaningless

Found while diagnosing that 40.1 % run, all committed to `../quality-bench`:

| Fix | Effect |
|---|---|
| `INSTRUCTIONS.md`: "a failing command is never a reason to stop; every turn while `_todo.py` reports remaining > 0 must end with a tool call" | HumanEval 0/30 → **29/30**, GSM8K 60/100 → 100/100 answered |
| `Dockerfile`: `python3-sympy numpy scipy` (plus a `.dockerignore`, since `docker build .` was shipping `runs/` as context) | MATH became answerable at all: 0 → 9 % (SQ-10) / 39 % (SQ-15) |
| `run.sh`: automatic relaunch of an incomplete bench (`BENCH_RETRIES`, default 2) with a "continue from where you stopped" prompt | Terminal 0/50 → **50/50** on the retry, MATH 50/100 → retried instead of silently scoring half |
| `bin/_progress.py`: idle kill 15 min → 8 min | a stalled container no longer eats 15 minutes per bench |
| `bin/_model_file.py`: resolves `.strata` packs, not just `.gguf` | reports show the pack, e.g. `Hy4-Flash-SQ-64` |

### Configurations these numbers were produced with

- **Hy4-Flash SQ-64**: `strata-hy4` 0.1.66 (built from Strata 0.2.20, HIP gfx1201),
  `--gpus 1,0 --layer-split auto`, `--vram-experts-gb 22`, `--max-context 81920`, `--kv q8`,
  DFly2 speculation on (K=7, adaptive tree), `reasoning_effort high` + 8 192-token budget,
  Engram-Q8 shard streamed from the SSD.
- **Inkling SQ-15 / SQ-10**: `strata-inkling` 0.1.66, `--max-context 131072`/`120000`, `--kv fp8`,
  `--cpu-threads 8`, `--draft off`, `reasoning_effort none` (the scored runs predate the 0.2
  default).
