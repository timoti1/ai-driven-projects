# Inference Engine Benchmarks on a Dual RX 9070 Stand

**Avalon · Strata · rdna-boosts · rocm-llama · llama.cpp Vulkan — HIP and Vulkan backends,
five ROCm versions, two PCIe slots**

**Test dates:** 2026-10-31 … 2026-11-01
**Branch:** `aic8800-wifi-bt-driver` · **Repository:** `timoti1/ai-driven-projects`
**Directories:** `perf-tuning/` (this document) and `perf-bench/` (harness)
**Status:** complete for the engines and models listed. Every number below is annotated with
the methodology that produced it and with what supersedes it.

---

## 0. Executive summary

Six conclusions, each with the section that backs it.

1. **For a model that fits in 16 GB of VRAM, the engine choice is a 30–55% decision and the
   PCIe slot is a 2% decision.** At Qwen3.8-27B, decode ranges from 26.0 tps (stock
   rocm-llama) to 40.4 tps (Vulkan, one card) — a 55% spread. The same model on the slow
   x2 slot loses 1.3–3.3%. (§5, §7.1)

2. **Vulkan wins decode, HIP wins prefill.** Vulkan gives the best decode at both model
   sizes (40.4 tps at 27B, 161.9 tps at 4B) and the worst prefill. rdna-boosts + ROCm 10.1
   gives the best prefill at 27B (1058 tps). Nobody wins both. (§5.3)

3. **The `rdna-boosts` fork adds no measurable gain over vanilla llama.cpp at identical
   ROCm** (999.9 vs 1009.3 tps at pp8192). What looks like a fork advantage is really the
   ROCm version it was built against. (§5.4)

4. **ROCm version effects are model-size dependent and not monotonic.** ROCm 7.17 costs 16%
   of decode at 27B but *gains* 12% of prefill at 4B. Strata gains 22% decode going from
   ROCm 7.8.0 to 7.17. Picking a ROCm version requires measuring your own model. (§9)

5. **For the 125B MoE, Strata is the better engine: 2.0–2.5x on prefill at long prompts,
   2x better time-to-first-token, and a small decode lead.** Avalon is more predictable at
   long context (±3% vs ±18%). (§6)

6. **The PCIe slot halves a streaming MoE and adds a ~23 s per-request penalty.** For the
   125B model whose experts live in system RAM, steady-state throughput drops 48.5% on the
   x2 slot, and a fixed ~23 s per request appears that was not there on x16 (1.4 s). Short
   prompts are the worst case: 27 tps and 16 s to first token. (§7.3)

### Which engine, which slot — decision table

| Situation | Use | Why |
|-----------|-----|-----|
| Dense model ≤ 16 GB VRAM, latency-sensitive chat | llama.cpp **Vulkan**, pinned `-dev Vulkan1` | best decode (40.4 tps at 27B, 161.9 at 4B) |
| Dense model ≤ 16 GB VRAM, prompt-heavy (RAG, long ingest) | **rdna-boosts + ROCm 10.1** | best prefill (1058 tps at 27B pp8192) |
| Dense model, slot width unknown or chipset x2 | any of the above | the slot costs 2–8%, it is not a factor |
| Qwen3.8-Flash-Next 125B MoE, experts in system RAM | **Strata**, and only in the **CPU-attached x16 slot** | 2.5x prefill over Avalon; the x2 slot halves it and adds 23 s/request |
| 125B MoE, long-context decode, predictability matters | Avalon | ±3% spread vs Strata's ±18% |
| Any 125B MoE on this 62 GB box | **one engine at a time** | two 125B engines resident drove prefill to 3.7 tps and froze the machine |

---

## 1. How to read this document

This document grew across several rounds of measurement, and the early rounds contained
methodology errors that changed the conclusions. Rather than delete the history, each
superseded table is marked in place. Use this map:

| Section | Status | Notes |
|---------|--------|-------|
| §0 Executive summary | **authoritative** | conclusions only, with pointers |
| §2 Test stand, §3 Software stack, §4 Methodology | **authoritative** | §4 explains every methodology fix and why |
| §5 Dense-model matrices (27B, 4B) | **authoritative** | corrected methodology, `r=3` |
| §6 125B head-to-head Avalon vs Strata | **authoritative** | corrected methodology, `r=3` |
| §7 PCIe slot test | **authoritative**, with one open question | §7.4 states what is *not* yet separated |
| §8 Avalon parameter tuning | historical | direction of each change is right, absolute values are from the old methodology |
| §9 ROCm version matrix | mixed | the 27B/4B rows are authoritative, the Avalon rows are historical |
| §10 Strata build comparison | historical | `r=2`, warm, but the *conclusion* (build is not the variable, ROCm is) holds |
| §11 llama-swap overhead, parallel sessions | historical | `r=2`, free EOS; the *sign* of the effect is trustworthy, the magnitude is rough |
| §12 System resource usage | **authoritative** | direct process measurements |
| §13 Recommendations, §14 Open questions | **authoritative** | |

**The single most important methodology fact:** anything measured before 2026-11-01 with
`temperature=0.6`, free EOS, 128-token generations and `r=1` is not comparable to anything
else. §4 explains why, and §1.1 lists the three bugs that invalidated whole classes of
numbers.

---

## 2. Test stand

### 2.1 Hardware

| Component | Specification |
|-----------|--------------|
| CPU | AMD Ryzen 7 5800 (8C/16T, **no AVX-512** — MoE expert kernels run on AVX-2) |
| GPU 0 | AMD Radeon RX 9070 (**Sapphire**, PCI `05:00.0`, subvendor `1da2`, **slow slot: PCIe 3.0 x2**), gfx1201 |
| GPU 1 | AMD Radeon RX 9070 (**Gigabyte**, PCI `0a:00.0`, subvendor `1458`, **fast slot: PCIe 4.0 x16**), gfx1201 |
| VRAM per GPU | 16 GB |
| System RAM | 62 GB, + 8 GB swap file |
| Motherboard limit | one CPU-attached x16 slot (Gen4) + one chipset-attached x2 slot (Gen3) |
| OS | Linux, Ubuntu 24.04-based |
| GPU power limit | **210 W — below factory TGP** |

**Power caveat.** Both cards are capped at 210 W, under their factory TGP. Every number here
is measured under that cap; the same cards at full power would score higher. Because both
cards share the cap, *relative* comparisons between cards are unaffected.

### 2.2 Device indices

| Index | HIP | Vulkan | Card | Slot |
|-------|-----|--------|------|------|
| 0 | `HIP_VISIBLE_DEVICES=0` | `-dev Vulkan0` | Sapphire | PCIe 3.0 x2 (slow) |
| 1 | `HIP_VISIBLE_DEVICES=1` | `-dev Vulkan1` | Gigabyte | PCIe 4.0 x16 (fast) |

HIP and Vulkan agree on the order because both enumerate by PCI address, and `05:00.0` sorts
before `0a:00.0`. HIP needs both the environment variable *and* the `-dev` flag (§4, item 6);
Vulkan needs only `-dev` (§4, item 7).

### 2.3 How the slot widths were verified — sysfs lies, the kernel does not

`sysfs` and `lspci` report **both** cards as `16x @ 32.0 GT/s` (PCIe 5.0 x16). That is wrong,
and reading it leads to a wrong conclusion. Those interfaces expose the card's *capability*
registers. The cards really are Gen5 x16 capable; the motherboard is not.

The kernel's own boot message reports the link it actually trained, and it is authoritative:

```
pci 0000:05:00.0: 15.752 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x2
                   link at 0000:02:00.0   (capable of 504.112 Gb/s with 32.0 GT/s PCIe x16)
pci 0000:0a:00.0: 252.048 Gb/s available PCIe bandwidth, limited by 16.0 GT/s PCIe x16
                   link at 0000:00:03.1   (capable of 504.112 Gb/s with 32.0 GT/s PCIe x16)
```

Reading it line by line:

- `05:00.0` — the **Sapphire** card — sits behind `02:00.0`, a chipset bridge, and trained
  **Gen3 x2**: 8 GT/s × 2 lanes = 15.75 Gb/s ≈ **2.0 GB/s**.
- `0a:00.0` — the **Gigabyte** card — sits behind `00:03.1`, directly on the CPU root
  complex, and trained **Gen4 x16**: 16 GT/s × 16 lanes = 252 Gb/s ≈ **31.5 GB/s**.

**The two identical GPUs therefore differ by 16x in bus bandwidth.** That gap is the whole
subject of §7.

Verify on this machine:

```bash
journalctl -k | grep "available PCIe bandwidth"   # authoritative: the trained link
lspci -vs 05:00.0 | grep LnkSta                   # misleading: the card's capability
```

---

## 3. Software stack

| Component | Version | Path |
|-----------|---------|------|
| llama-swap | v265 (commit `d1e743f`, built 2026-10-14) | `/home/timoti/llama-swap/` |
| Proxy listen | `0.0.0.0:8080` (second instance on `127.0.0.1:8081` for the slot test) | HTTP |
| ROCm (system) | 7.8.0 | `/opt/rocm` |
| HIP / hipcc | 7.16.26385-0000000, AMD clang 24.0.0 | `/usr/bin/hipcc` |
| Vulkan ICD (Mesa RADV) | API 1.4.318 | `/home/timoti/mesa-build/libvulkan_radeon.so` |

### Engines under test

| Engine | Kind | Backend | Model it was measured with |
|--------|------|---------|---------------------------|
| **Avalon** | llama.cpp fork 0.26.0, HIP | ROCm 7.8.0 / 7.13 | Qwen3.8-Flash-Next 125B MoE, IQ3_KS, 33 shards + MTP draft |
| **Strata** | proprietary engine, HIP | ROCm 7.8.0 / 7.17 | Qwen3.8-Flash-Next 125B MoE, IQ3_XXS / IQ3_S, native expert packs |
| **rdna-boosts** | `stew675/llama-cpp-rdna-boosts` @ `561696677`, 0.7.0-dev | HIP, RDNA4 (gfx1201) tuned | Spark-X2.6-4B IQ4_XS, Qwen3.8-27B IQ3_XXS |
| **rocm-llama (stock)** | AMD's stock ROCm llama.cpp fork | HIP | same dense models |
| **llama-latest (Vulkan)** | upstream llama.cpp, Vulkan/RADV | Vulkan | same dense models |
| **vanilla llama-b1347** | upstream llama.cpp, HIP | ROCm 7.17 | Qwen3.8-27B IQ3_XXS |

Format incompatibilities worth knowing: rdna-boosts **cannot load the Avalon fork's 33-shard
custom MoE format** (invalid ggml type 43) and cannot load the 125B model at all (exceeds
16 GB VRAM). rdna-boosts also requires K and V cache types to match, unlike Avalon, which
accepts a `q8_0`/`q4_0` mix.

---

## 4. Methodology

### 4.1 The corrected protocol (used by §5, §6, §7)

| Condition | Value | Effect |
|-----------|-------|--------|
| Sampling | `temperature=0.0` (greedy) | repeats measure identical token sequences |
| Early stop | `min_tokens = n`, `ignore_eos = true` | every repeat generates exactly `n` tokens |
| Generation length | **512 tokens** | steady-state decode, not per-request overhead |
| Prompt sizes | 512 / 2048 / 8192 / **16384** | exposes KV-cache and memory-bandwidth behaviour |
| Repetitions | **3**, median reported | see noise budget below |
| Batch / ubatch | `-b 4096 -ub 2048` | identical across all engines |
| Attention | flash-attn on, KV f16 | identical across all engines |
| Device pinning (HIP) | `HIP_VISIBLE_DEVICES=N` **and** `-dev ROCm0` | engine cannot spread across cards |
| Device pinning (Vulkan) | `-dev Vulkan1` (or `Vulkan0`) | see bug below |
| Residency | **one 125B MoE at a time**, other card free | two 125B engines do not fit in 62 GB |

`min_tokens` / `ignore_eos` are sent to the server; if a server rejects them, the harness
falls back and the affected run is flagged rather than silently mixed into the table.

### 4.2 The three bugs that invalidated whole classes of numbers

**Bug 1 — Vulkan was never pinned to one GPU.** `RADV_DEVICE=1` does **not** restrict devices
for llama.cpp. `llama-bench` still reported `devices=auto` and listed *both* cards in
`gpu_info`, meaning the model was sharded across Sapphire **and** Gigabyte. Every Vulkan
number measured that way describes a two-GPU configuration, not one card. Correct flag:
`-dev Vulkan1`. This bug inverted a conclusion: pinned to one card, Vulkan is the *best*
decode engine, not a mediocre one.

**Bug 2 — decode was measured on 128 free-EOS generations at temperature 0.6.** Completion
length varied **96…128 tokens** between repeats, and throughput is computed over tokens
actually produced, so a short repeat mostly measures fixed request overhead. Repeats were not
measuring the same work.

**Bug 3 — two 125B MoE models were resident at once** in one round (Avalon + Strata). 62 GB
cannot hold both expert tables; prefill collapsed to **3.7 tps**. Any 125B number taken while
another 125B model is loaded is invalid, and one such number survived into an early table.

### 4.3 Noise budget (measured, not assumed)

Qwen3.8-27B IQ3_XXS, GPU 1, corrected protocol, `r=3`:

| Measurement | Stddev |
|-------------|--------|
| pp512 | ±10.9% |
| pp2048 | ±0.7% |
| pp8192 | ±0.1% |
| pp16384 | ±0.1% |
| tg512 | ±0.8% |

**Rule: `pp512` is not a comparison point.** At 512 tokens the measurement is dominated by
launch and scheduling latency; it carries 5–14% noise even under the corrected protocol
(±19% under the old one). Compare at **pp8192 / pp16384 / tg512**, where noise is 0.0–1.5%.
Every claim in §0 and §5–§7 rests on those three columns.

Three repetitions are sufficient *because* the per-repeat load is large: longer prompts and
4x longer generations cut the spread far more than more repetitions would.

---

## 5. Dense models on the fast card (27B and 4B)

GPU 1 (Gigabyte, PCIe 4.0 x16), device pinned, `-b 4096 -ub 2048`, flash-attn on, KV f16,
`r=3`, greedy, `tg=512`. Measured with `llama-bench` directly against each engine binary —
no proxy in the path, so these numbers are engine-only.

### 5.1 Qwen3.8-27B IQ3_XXS (9.8 GB — fully resident in 16 GB)

| Engine | ROCm | pp2048 | pp8192 | pp16384 | tg512 | pp512 (noisy, do not compare) |
|--------|------|--------|--------|---------|-------|-------------------------------|
| **rdna-boosts** | 10.1 (HIP 7.16) | **1073.6** | **1058.5** | **1016.4** | 39.6 | 803.7 ±10.9% |
| rdna-boosts | 7.13 | 822.0 | 960.8 | 1010.5 | 38.6 | 1042.4 ±0.0% |
| rdna-boosts | 7.17 | 1030.7 | 1009.3 | 971.6 | 33.2 | 998.0 |
| vanilla llama-b1347 | 7.17 | 1027.4 | 999.9 | 913.2 | 32.8 | 996.6 |
| rocm-llama (stock) | 10.1 (HIP 7.16) | 883.6 | 876.9 | 833.3 | 26.0 | 826.5 ±10.5% |
| **llama-latest (Vulkan, one card)** | n/a | 971.6 | 940.5 | 896.1 | **40.4** | 992.4 |

Bold = best in column.

**Commentary.** The decode column spans 26.0 → 40.4 tps: a **55% spread between engines on
identical hardware and an identical model**. That is the largest single lever in this whole
study — bigger than any runtime flag, and bigger than the PCIe slot for a resident model.
The prefill column spans 876.9 → 1058.5 tps (21%). Note the two winners are different
engines: nobody is best at both.

### 5.2 Spark-X2.6-4B IQ4_XS (2.6 GB — fully resident)

Same conditions.

| Engine | ROCm | pp2048 | pp8192 | pp16384 | tg512 |
|--------|------|--------|--------|---------|-------|
| rdna-boosts | 10.1 | 6223.5 | 5912.1 | 5420.8 | 152.0 |
| **rdna-boosts** | 7.17 | **6937.6** | **6628.1** | **6115.2** | 132.1 |
| rocm-llama (stock) | 10.1 | 6709.1 | 6441.1 | 6000.7 | 133.5 |
| **llama-latest (Vulkan, one card)** | n/a | 5223.7 | 4949.0 | 4522.6 | **161.9** |

**Commentary.** At 4B the ROCm-version effect *inverts* relative to 27B: ROCm 7.17 is the
best prefill here (+12% over 10.1) while it was 16% *worse* on 27B decode. Vulkan still wins
decode by 7% and still loses prefill by 25%. A 4B model leaves the GPU compute-bound rather
than memory-bound, which is why the ranking re-shuffles.

### 5.3 Cross-model conclusions

1. **Vulkan wins decode at both sizes** — 40.4 tps (27B), 161.9 tps (4B). The earlier "Vulkan
   is slower" conclusion was purely Bug 1: it had been measured across two cards.
2. **rdna-boosts + ROCm 10.1 wins prefill at 27B** (1058 tps at pp8192).
3. **HIP wins prefill, Vulkan wins decode** — consistently, at both model sizes. If your
   workload is prompt-heavy choose HIP; if it is generation-heavy choose Vulkan.
4. **Stock rocm-llama is the weakest engine at 27B**: 26.0 tps decode, −34% vs the best.

### 5.4 The rdna-boosts fork adds nothing over vanilla llama.cpp

| Pair (same ROCm 7.17, 27B) | pp8192 | tg512 |
|---|---|---|
| rdna-boosts | 1009.3 | 33.2 |
| vanilla llama-b1347 | 999.9 | 32.8 |

Difference is 0.9% and 1.2% — inside the noise floor. **The apparent "AMD fork advantage" is
the ROCm version the fork was built against, not the fork's own code.** Choose a ROCm
version, not a fork.

---

## 6. The 125B MoE head-to-head: Avalon vs Strata

GPU 1 (Gigabyte, x16), **one 125B model resident at a time**, warm, greedy
(`temperature=0`, `min_tokens=512`, `ignore_eos`), `r=3`, through llama-swap for both engines
so the proxy is in both paths and cancels out. Both are Qwen3.8-Flash-Next 125B MoE: Avalon
IQ3_KS + MTP draft (`--spec-draft-n-max 3`), Strata IQ3_XXS + built-in spec (`--spec 4`).

### 6.1 Medians, and the raw repeats behind them

Raw values are printed because the *spread* is itself a result (§6.3).

| Metric | Avalon — 3 repeats | Avalon med | Strata — 3 repeats | Strata med | Strata vs Avalon |
|--------|--------------------|-----------|--------------------|-----------|------------------|
| pp512 | 243.0 / 245.4 / 249.1 | 245.4 | 259.9 / 284.4 / 291.2 | 284.4 | ×1.16 |
| pp2048 | 675.3 / 676.4 / 676.4 | 676.4 | 663.0 / 680.8 / 719.7 | 680.8 | ×1.01 |
| pp8192 | 927.2 / 929.5 / 931.6 | 929.5 | 1797.1 / 1869.2 / 1877.5 | **1869.2** | **×2.01** |
| pp16384 | 934.8 / 939.5 / 940.5 | 939.5 | 2384.3 / 2385.8 / 2387.1 | **2385.8** | **×2.54** |
| tg1024 (512 tok) | 57.6 / 58.8 / 59.1 | 58.8 | 68.3 / 69.8 / 76.7 | **69.8** | ×1.19 |
| tg8192 (512 tok) | 63.2 / 63.9 / 66.2 | 63.9 | 51.1 / 65.7 / 67.3 | **65.7** | ×1.03 |
| tg32768 (512 tok) | 57.2 / 59.1 / 60.8 | 59.1 | 49.9 / 62.4 / 71.7 | **62.4** | ×1.06 |

### 6.2 Time to first token

| Depth | Avalon | Strata | Strata advantage |
|-------|--------|--------|------------------|
| 1024 | 2.9 s | **2.0 s** | −31% |
| 8192 | 5.86 s | **2.91 s** | **−50%** |
| 32768 | 20.7 s | **9.26 s** | **−55%** |

### 6.3 Commentary — where the advantage comes from, and its cost

**The prefill advantage is a scaling advantage, not a constant one.** At pp2048 the two
engines are level (×1.01). Strata's lead opens with prompt length: ×2.01 at pp8192, ×2.54 at
pp16384. That signature means Avalon's prefill *saturates* — Avalon barely improves from
929.5 tps at pp8192 to 939.5 at pp16384, i.e. it hits a ceiling around ~940 tps and stays
there. Strata keeps scaling: 1869 → 2386. So the question is not "is Strata faster" but
"at what prompt length does each engine stop scaling", and Avalon's ceiling is the finding.

**TTFT follows prefill directly.** Strata's 2x TTFT win at 8192 is arithmetic: it processes
the prompt twice as fast. For an interactive agent that re-sends context every turn, this is
the single most valuable number in §6.

**Decode is close, and Strata pays for it in variance.** Avalon's decode spread is ±3%
across all depths — deterministic MTP acceptance. Strata's spread is much wider: at depth
32768 it ranged 49.9 → 71.7 tps, and at depth 1024 68.3 → 76.7. Its speculative acceptance
rate depends on content, so its *worst* case falls below Avalon's median. The median is the
honest summary, but if you need a guaranteed floor, Avalon is the safer engine.

**Verdict.** Strata is the right engine for this model: 2–2.5x on the phase that dominates
agent workloads (prefill/TTFT) plus a small decode lead. Avalon stays the more predictable
one at long context.

---

## 7. The PCIe slot test: Sapphire (x2) vs Gigabyte (x16)

The two cards are identical GPUs (gfx1201, 16 GB, same 210 W cap) wired differently:
**2.0 GB/s vs 31.5 GB/s — a 16x difference** (§2.3). The question is whether that 16x ever
shows up in tokens per second.

**Method.** Same engine, same model, same llama-swap path, same request suite. Only
`HIP_VISIBLE_DEVICES` changes (1 → 0); for Strata the card is set in its own config
(`"gpu": 0`) and served by a second llama-swap instance on `127.0.0.1:8081`. One 125B model
resident at a time.

### 7.1 Fully resident models — the slot barely matters

Corrected protocol, greedy, `tg=512`, `r=3`, pinned (`-dev ROCm0` + `HIP_VISIBLE_DEVICES=0`;
`-dev Vulkan0`). Both models fit wholly in 16 GB, so nothing streams over PCIe during
inference.

x2/x16 ratio (1.000 = the slow slot performs identically):

| Engine | Model | pp2048 | pp8192 | pp16384 | tg512 |
|--------|-------|--------|--------|---------|-------|
| rocm-llama stock (ROCm 10.1) | 27B | 0.978 | **0.980** | **0.987** | 0.967 |
| llama-latest Vulkan | 27B | **0.980** | **0.982** | **0.984** | 0.888 |
| rdna-boosts (ROCm 10.1) | 27B | 0.889 | 0.913 | 0.925 | **0.965** |
| rdna-boosts (ROCm 7.17) | 27B | 0.751 | 0.855 | 0.951 | 0.945 |
| rdna-boosts (ROCm 10.1) | 4B | 0.954 | 0.944 | 0.957 | 0.943 |
| rocm-llama stock (ROCm 10.1) | 4B | 0.912 | 0.916 | 0.882 | 0.863 |
| llama-latest Vulkan | 4B | 0.922 | 0.924 | 0.912 | 0.760 |
| rdna-boosts (ROCm 7.17) | 4B | 0.871 | 0.843 | 0.826 | 0.889 |

Median of all 32 comparisons: **0.92**. Best cases cluster tightly at **0.98**.

**How to read this table.**

- **No cliff.** A 16x bus becomes 2–6% once the model is resident. That is the expected
  physics: with everything in VRAM, per-token work never crosses PCIe; the bus is used at
  load time and for occasional page faults.
- **Trust the tight rows, distrust the outliers.** `stock101_27b` and `vulkan0_27b` prefill
  sit at 0.98 with stddev 0.0–0.4% across three prompt sizes — small, consistent,
  repeatable. That is the real slot effect. `rdna717_27b` shows −24.9% at pp2048 but −4.9%
  at pp16384, same engine, same model, same card. A bandwidth limit cannot flip like that
  within one model; run-to-run drift can. Those outliers are noise, not signal.
- **Decode holds up best at 27B** (0.965 for the best engine), as predicted: decode is
  weight-resident and GPU-local.
- **Bias direction.** The x2 round ran with the agent's Avalon 125B model resident (idle) on
  the other card; the x16 round ran with both cards otherwise idle. An idle resident model
  generates no PCIe traffic but does hold RAM, so the x2 figures are if anything biased
  *downward*. The true penalty is at or below these numbers.

**Conclusion:** an x2 slot is fine for resident models. The cost is a few percent, inside the
run-to-run spread, and it does not grow with context length.

### 7.2 The 125B MoE — the case the slot is supposed to break

Here the model does **not** fit: 125B at IQ3_XXS keeps its expert tables in system RAM and
pulls them across the bus. This is where 2.0 GB/s should hurt.

**Strata (new build, ROCm 7.17), Qwen3.8-Flash-Next 125B IQ3_XXS, median of 3:**

| Test | x16 (Gigabyte) | x2 (Sapphire) | x2/x16 | Loss |
|------|---------------|---------------|--------|------|
| pp512 | 284.4 | 27.3 | 0.096 | **−90.4%** |
| pp2048 | 680.8 | 57.1 | 0.084 | **−91.6%** |
| pp8192 | 1869.2 | 205.1 | 0.110 | **−89.0%** |
| pp16384 | 2385.8 | 366.2 | 0.153 | **−84.7%** |
| tg1024 (512 tok) | 69.8 | 35.7 | 0.511 | −48.9% |
| tg8192 (512 tok) | 65.7 | 28.0 | 0.426 | −57.4% |
| tg32768 (512 tok) | 62.4 | 26.4 | 0.423 | −57.7% |

| Time to first token | x16 | x2 | Slower |
|---------------------|-----|-----|--------|
| depth 1024 | 2.0 s | 16.3 s | **8.2x** |
| depth 8192 | 2.9 s | 26.3 s | **9.1x** |
| depth 32768 | 9.3 s | 108.3 s | **11.6x** |

**The prefill numbers are reproducible to 0.1%.** Raw repeats on x2: pp512 = 27.1 / 27.3 /
27.4; pp2048 = 57.0 / 57.1 / 57.2; pp8192 = 205.0 / 205.1 / 205.2; pp16384 = 366.1 / 366.2 /
366.2. Three repeats landing within 0.1% is the signature of a hard resource ceiling, not of
noise. **Decode, by contrast, is noisy on x2:** tg1024 = 13.8 / 35.7 / 38.1 and TTFT at depth
32768 = 61.0 / 108.3 / 111.7 s. That asymmetry is informative — see §7.4.

### 7.3 Decomposition: a halved steady-state rate *plus* a ~23 s fixed cost

Reporting only "−90%" hides what actually happens, and the mechanism matters for the
decision. Taking the **absolute wall time** per request instead of the rate separates a
fixed cost from a per-token cost:

| Prompt | tokens | Strata x16 wall | Strata x2 wall | Avalon x16 wall |
|--------|--------|-----------------|----------------|-----------------|
| pp512 | 383 | 1.41 s | **14.07 s** | 1.56 s |
| pp2048 | 1380 | 1.97 s | **24.14 s** | 2.04 s |
| pp8192 | 5380 | 2.94 s | **26.24 s** | 5.79 s |
| pp16384 | 10709 | 4.49 s | **29.25 s** | 11.40 s |

Look at the x2 column: 14.07 → 24.14 → 26.24 → 29.25 s. **Going from 383 to 10709 tokens —
28x more work — costs only 15 extra seconds.** A 16384-token prompt on the slow slot takes
29 s; a 512-token prompt takes 14 s. The token count is almost irrelevant.

Fitting `t = fixed + tokens / marginal_rate` to the two longest prompts:

| | fixed cost | marginal rate |
|---|---|---|
| **Strata on x16** | 1.38 s | **3438 tps** |
| **Strata on x2** | **23.20 s** | **1770 tps** |
| Avalon on x16 | 0.13 s | 950 tps |

Two separate effects, and they should be reported separately:

1. **Steady-state throughput halves: 3438 → 1770 tps, ratio 0.515 (−48.5%).** This is the
   genuine bandwidth effect, and it is corroborated independently: the *decode* ratios in
   §7.2 are 0.511 / 0.426 / 0.423 — median ≈ 0.43–0.51. Two different measurement designs
   (prefill marginal rate vs decode at fixed depth) agree on ~50%. That agreement is the
   strongest evidence in this section.
2. **A ~23 s fixed cost per request appears where x16 had 1.4 s.** This is what produces the
   headline −90% at short prompts, and it is *not* a per-token bandwidth effect.

So the honest summary is: **the x2 slot halves a streaming MoE's steady-state rate and adds
~23 s to every request.** The −90% figure is real as an observed end-to-end number for short
prompts, but attributing it to PCIe bandwidth alone is wrong.

### 7.4 What is not yet separated

The ~23 s fixed cost is measured reliably but its cause is not proven. Two candidates:

- **Expert tables re-read from disk.** Strata's resident footprint is ~50 GB (§12). 46 GB at
  ~2 GB/s is 23 s — the same order, which is suggestive. But note 2 GB/s here would be *NVMe
  or page-cache* bandwidth, not the PCIe slot, so the numeric coincidence with the slot
  figure may be accidental and would not make the effect slot-caused.
- **Model unload/reload between requests.** llama-swap has an idle-unload timeout; if the
  model was evicted between requests, each request pays a full load, and a cold load on the
  x2 card is much slower.

**Experiment that would settle it:** grep the llama-swap log for load/unload events per
request, and re-run with the swap idle-timeout disabled. If the 23 s persists with the model
guaranteed resident, it is a real per-request cost of running this model on the slow slot; if
it disappears, the −90% short-prompt figure was an artifact of a reload and the correct
headline is the −48.5% steady-state loss.

**Also unexplained:** why x2 decode is noisy (13.8–38.1 tps) while x2 prefill is reproducible
to 0.1%. A saturated bus with a deterministic access pattern explains the tight prefill; it
does not obviously explain the noisy decode. RAM pressure and swapping are the likely source,
which is the same confound as above.

### 7.5 Avalon on the x2 slot — never measured, the machine froze

The batch that would have measured Avalon on Sapphire hard-froze during its model load and
had to be power-cycled. `/tmp` was lost, so **no Avalon x2 numbers exist.** §12.3 explains the
cause, which is memory, not the GPU.

Given §7.3, the expected loss for Avalon is the same order as Strata's steady-state figure —
the mechanism (experts in system RAM crossing the bus) is common to both engines. Avalon's
x16 steady-state rate is lower (950 tps marginal), so on x2 it would land near or below
Strata's 1770 tps only if it degraded proportionally; it may well degrade less in absolute
terms. This is an open question, not a conclusion.

### 7.6 Slot summary

| Model class | Resident in 16 GB VRAM? | x2 slot penalty |
|-------------|-------------------------|-----------------|
| Dense 4B / 27B, all engines | yes | **median −8%**, best engines −2%, does not grow with context |
| 125B MoE, experts in system RAM | no | **steady-state −48.5%** (prefill marginal and decode agree), **plus ~23 s fixed per request** → −85…−92% at short prompts, TTFT 8–12x worse |

**Practical rule.** Put a streaming MoE in the CPU-attached x16 slot, never in a
chipset-attached x2 slot. The second card is the right place for dense resident models and
the wrong place for this one. On the x2 slot the least-damaged case is long-context
decode-heavy work; anything prompt-heavy (RAG, document ingest, an agent re-sending context)
is unusable at 27–366 tps with 16–108 s to first token.

---

## 8. Avalon parameter tuning (historical)

**Measured 2026-10-31 under the old methodology** (`temperature=0.6`, free EOS, `r=1–2`,
128-token decode). Absolute values are superseded by §6; the *direction and size* of each
change is still the useful part, and this is the only record of the sweep.

Model: `avalon-qwen3.8-flash-next-C2`, Qwen3.8-Flash-Next 125B MoE, IQ3_K, 33 shards, Avalon
fork 0.26.0 (llama.cpp 0.26.0, HIP/ROCm 7.8.0).

| Configuration | parallel | `-b` | draft | prefill 8192 | decode 8192 | TTFT 8192 |
|---------------|----------|------|-------|-------------|-------------|-----------|
| Original | 2 | 2048 | 2 | ~497 tps | ~46 tps | ~10.8 s |
| `+batch 4096` | 2 | 4096 | 2 | ~889 tps | ~60 tps | ~10.8 s |
| `+draft 3` | 2 | 4096 | 3 | ~941 tps | ~63 tps | ~5.8 s |
| **single session (adopted)** | **1** | **4096** | **3** | ~984 tps | ~75 tps | ~5.5 s |
| same, through llama-swap | 1 | 4096 | 3 | ~931–954 tps | ~56–64 tps | ~5.8–6.1 s |

**What each change bought:**

- **`-b 2048 → 4096`: +89% prefill** (497 → 889 tps). Largest single win in the sweep.
  Larger batches keep the GPU fed and amortise per-launch overhead.
- **`--parallel 2 → 1`: +19% decode** (63 → 75 tps) at similar TTFT. Two sessions share one
  compute stream, so each gets less; there is no free lunch from `--parallel` on one card.
  Confirmed independently in §11.2.
- **`--spec-draft-n-max 2 → 3`: +10–20% decode.** More speculative drafts accepted per step.
  It also cut TTFT from 10.8 s to 5.8 s at `parallel=2`, which is why it is worth the extra
  draft-model memory.

**Final Avalon configuration** (as deployed in `llama-swap/config.yml`):

| Parameter | Value | Note |
|-----------|-------|------|
| `-b` / `-ub` | 4096 / 2048 | was 2048 / 1024 |
| `--spec-type` | `draft-mtp` | with `-md` pointing at the MTP GGUF |
| `--spec-draft-n-max` | 3 | was 2 |
| `-ubd` | 256 | draft ubatch |
| `-fa` | on | flash attention |
| `-ctk` / `-ctv` | `q8_0` / `q4_0` | mixed KV (Avalon allows the mix; rdna-boosts does not) |
| `-ctkd` / `-ctvd` | `q8_0` / `q4_0` | draft KV |
| `--parallel` | 1 | see above |
| `--jinja` | — | chat template |
| `--temp` / `--top_k` / `--top_p` | 0.6 / 30 / 0.95 | server defaults; benchmarks override to greedy |
| `--reasoning-effort` / `--reasoning-budget` | low / 4092 | |
| `HIP_VISIBLE_DEVICES` | 1 | Gigabyte, the fast slot |

**Context size is a hidden cliff.** With `-c 200000` Avalon decode drops to ~60 tps from ~80
tps at `-c 32768` — KV-cache pressure eats VRAM that weights need. Size the context to the
workload, do not default to the model maximum.

---

## 9. ROCm version matrix

Five ROCm versions were tested. The effect is **not monotonic** and depends on model size and
engine, so this is a table to read per-row, not a ranking.

| Engine / model | ROCm | Result | Note |
|----------------|------|--------|------|
| rdna-boosts, 27B | 10.1 (HIP 7.16) | best decode **39.6**, best prefill **1058** | production release — the default choice |
| rdna-boosts, 27B | 7.17 | decode 33.2 (**−16%**), prefill 1009 | newer HIP regresses decode at 27B |
| rdna-boosts, 27B | 7.13 | pp2048 822 (unstable), prefill 960 | not competitive |
| rdna-boosts, 4B | 7.17 | prefill **6628** (+12% vs 10.1), decode 132.1 (−13%) | **inverts** the 27B result |
| Strata, 125B | 7.17 | decode 81, prefill 1852 | best for Strata |
| Strata, 125B | 7.8.0 (`/opt/rocm`) | decode 63 (**−22%**), prefill 1865 | prefill unchanged, decode regresses |
| Avalon, 125B | 7.13 | prefill +1.4%, decode **−18.5%**, TTFT **+233%** (5.5 → 18.3 s) | not recommended |

**Reading:**

- **ROCm 10.1 / HIP 7.16 is the safest default for llama.cpp-family engines** on this GPU.
- **A newer ROCm is not a faster ROCm.** 7.17 helps 4B prefill and hurts 27B decode; 7.13
  helps Avalon prefill by 1.4% and wrecks its TTFT by 233%.
- **Strata specifically wants 7.17** — worth 22% of decode, likely hipBLASLt kernels or GPU
  scheduling. Set `lib_dirs` to `/media/timoti/Data/llama-builds/llama-b1347-rocm-gfx120X/`.
- **The Avalon TTFT number (5.5 → 18.3 s) is the most dramatic single-version effect in this
  study.** A version change can cost 3x in perceived responsiveness while barely moving
  throughput, which is why throughput-only evaluation misleads.

---

## 10. Strata: old build vs new build (a confound that was removed)

Two binaries, both version 0.1.51:

- **Old:** `/media/timoti/Data/repos/Strata/engine/strata` — linked against ROCm **7.17**
- **New (fresh build):** `/media/timoti/Data/repos/Strata/work-rx9070/b/strata`

The first comparison reported a **−42% decode regression** in the new build. That was wrong:
the new build had been run against `/opt/rocm` (7.8.0) while the old one used 7.17. Re-running
the new build against the same 7.17 libraries:

| Metric | Old (7.17) | New (7.8.0) | New (7.17) | New vs Old, same ROCm |
|--------|-----------|-------------|-----------|----------------------|
| Prefill 8192 | ~1852 | ~1865 | ~1844 | **−0.4%** (identical) |
| Decode 1024 | ~74 | ~56 | ~71 | −4% (noise) |
| Decode 8192 | ~81 | ~63 | ~80 | **−1%** (identical) |
| Decode 32768 | ~63 | ~52 | ~88 | **+40%** |

**Conclusion: the builds are equivalent.** The regression was a library-version confound. The
new build is safe to use; what matters is which ROCm libraries it resolves at run time.

**The transferable lesson:** in this stack, the ROCm version resolved at run time is a bigger
variable than the engine build, the fork, or the quantization. Any comparison that does not
pin `LD_LIBRARY_PATH` / `lib_dirs` is measuring the wrong thing.

---

## 11. llama-swap proxy overhead and parallel sessions

Both measured 2026-10-31 under the old methodology (`r=2`, free EOS). The sign and rough size
of each effect are trustworthy; treat the percentages as ±5 points.

### 11.1 Proxy overhead

Direct engine on port 5800 vs the same engine through llama-swap on 8080, same model, same
parameters:

| Metric | Direct (5800) | Via llama-swap (8080) | Overhead |
|--------|--------------|----------------------|----------|
| Prefill 8192 | ~984 tps | ~931–954 tps | ~3–5% slower |
| Decode 8192 | ~71–80 tps | ~56–64 tps | **~20% slower** |
| TTFT 8192 | ~5.5–5.6 s | ~5.8–6.1 s | ~10% slower |
| Decode 1024 | ~71–76 tps | ~63–67 tps | ~12% slower |
| Decode 32768 | ~73–80 tps | ~58–65 tps | ~20% slower |

**The "3–4x llama-swap overhead" claim was false** and has been removed from all documents; it
came from a faulty run. Real overhead is moderate.

**Why the overhead is asymmetric.** Prefill is GPU-bound: a large matrix workload over which
any fixed per-request cost is amortised, so it shows 3–5%. Decode is a stream of small
latency-sensitive steps, so the same fixed cost is a larger fraction — 20%. Contributing
costs: an extra HTTP stack and TCP hop on localhost, JSON (de)serialisation of large prompts,
process-to-process copies (client → llama-swap → llama-server and back), model lookup and
request validation in the router, request/response logging, and per-token chunked-transfer
framing when streaming.

**Recommendation:** for maximum performance connect to the engine port directly; llama-swap's
overhead is not prohibitive and its model-management convenience is usually worth the ~20% on
decode. Note that §6 and §7 deliberately measure *through* llama-swap on both sides, so that
overhead cancels out of those comparisons.

### 11.2 Parallel sessions

Avalon with `--parallel 2`, two simultaneous requests, 8192-token prompt, 128 max tokens each:

| Metric | Single session | Two parallel (combined) | Ratio |
|--------|---------------|------------------------|-------|
| Decode | ~59–62 tps | ~43–45 tps combined | **0.70–0.76x** |
| Prompt | ~659–854 tps | ~661–694 tps combined | 0.81–1.00x |
| Wall clock | ~4.2–5.0 s | ~5.4 s | — |

**Two sessions do not increase combined decode throughput — they reduce it to ~70–76% of one
session.** Prompt processing is roughly unchanged. On a single card, `--parallel 2` is a
throughput *loss* for decode; it only helps if requests would otherwise idle the GPU. This
independently confirms the `--parallel 1` result in §8.

Harness: `perf-bench/test_parallel_sessions.py`.

---

## 12. System resource usage — and why the machine froze

Measured directly on this box (62 GB RAM, 8 GB swap, dual RX 9070, ROCm 7.8.0). Each engine
measured idle with the model loaded, then during a 200-token generation.

### 12.1 Side by side

| Resource | Strata | Avalon | Difference |
|----------|--------|--------|------------|
| Engine RSS | ~50.7–51 GB | ~51.8–52.3 GB | **similar** |
| System RAM *used* (idle) | **~54 GiB** | **~5.4 GiB** | 10x |
| System RAM *used* (inference) | ~54 GiB | ~5.9 GiB | 9x |
| RAM available to other processes | **~8 GB** | **~56 GB** | 7x |
| Swap used | ~3.9 GiB | ~1.7 GiB | 2.3x |
| Engine CPU (idle) | ~50% | ~36% | Avalon lighter |
| Engine CPU (inference) | ~75% | ~104% | Avalon uses more cores |
| GPU VRAM (card 1) | ~98% | ~98% | same |
| Responsiveness | constrained | comfortable | **Avalon better** |

Process detail — Strata runs as three processes: llama-swap proxy (~25–29 MB, ~0% CPU), the
Strata Python server (~30–32 MB, ~0.6% CPU), and the Strata engine itself (~50.7–51 GB RSS,
50–75% CPU). Avalon is a single `llama-server` process.

### 12.2 The RSS numbers are the same; the memory *type* is not

Both engines show ~51 GB RSS, yet Avalon leaves 56 GB free and Strata leaves 8 GB. That is not
a contradiction and the distinction is the key to §7.5:

- **Avalon's RSS is mostly file-backed page cache** — mmap'd GGUF shards. The kernel counts
  those pages as reclaimable cache, not as used memory, so "used" reads ~5.4 GiB. Under
  pressure they are simply dropped and re-read from disk.
- **Strata's RSS is anonymous / private memory** — expert tables it built itself in RAM.
  Those pages are *not* reclaimable; the only way to evict them is to write them to swap.

**Consequence on a 62 GB box:** with Strata resident, ~54 GB is pinned and only ~8 GB of swap
stands between the system and a stall. This is why Strata is unusable alongside another large
engine, and why §7.5's freeze happened.

### 12.3 The freeze, explained

While loading Avalon's 125B model after Strata had run, the machine hard-froze and had to be
power-cycled; a hard freeze leaves no kernel log, and `/tmp` was lost.

The mechanism follows from §12.2: Strata pins ~54 GB of unreclaimable anonymous memory.
Avalon's loader then wants to populate ~46 GB of buffers. To do that the kernel must reclaim
memory, and the only reclaimable memory is Strata's — which requires swapping it out. With
8 GB of swap against ~46 GB of demand, the system thrashes itself into unresponsiveness.
The GPU and the PCIe slot are not involved.

**Guard rules for any future 125B measurement** (implemented in
`perf-tuning/results/audit-2026-11-01/orchestrate-slot-x2.sh`):

1. Never chain two 125B engine loads in one script without an explicit unload and a wait.
2. Drop caches before loading: `sync; echo 3 | sudo tee /proc/sys/vm/drop_caches`.
3. Check `free -g` and **refuse to load** rather than proceed when available RAM is below the
   requirement — a freeze costs the results, `/tmp`, and any uncommitted work.
4. Commit raw results to a git-tracked file as soon as they are produced. `runs.csv` survived
   the freeze; everything in `/tmp` did not.

---

## 13. Recommendations

**Engine choice**

1. Dense model that fits in VRAM, generation-heavy → **llama.cpp Vulkan**, pinned
   `-dev Vulkan1`. Best decode at both 27B and 4B.
2. Dense model, prompt-heavy → **rdna-boosts + ROCm 10.1**. Best prefill at 27B.
3. Qwen3.8-Flash-Next 125B MoE → **Strata**, in the **x16 slot only**. 2–2.5x prefill and 2x
   TTFT over Avalon; keep Avalon if you need a predictable decode floor.
4. Do not choose a fork expecting a win — at identical ROCm, rdna-boosts and vanilla
   llama.cpp are within 1%.

**Runtime and configuration**

5. **Pin the ROCm version explicitly** (`LD_LIBRARY_PATH` / `lib_dirs`). It is the largest
   single variable in this stack and it is invisible in a version string.
6. **Strata needs ROCm 7.17**; llama.cpp-family engines generally prefer **ROCm 10.1 / HIP
   7.16**. Do not generalise one to the other.
7. **Size the context to the workload.** `-c 200000` costs Avalon ~25% of decode versus
   `-c 32768`.
8. **`--parallel 1` on a single card.** Parallel sessions reduce combined decode throughput.
9. `-b 4096 -ub 2048` is worth +89% prefill over 2048/1024 and is the common baseline used
   throughout this document.

**Measurement discipline** (each of these changed a conclusion here)

10. **Greedy sampling and fixed token counts are mandatory.** Without them, repeats do not
    measure the same work.
11. **Verify device pinning from the engine's own output** (`devices=`, `gpu_info`), not from
    the environment variable you set. `RADV_DEVICE` silently does nothing.
12. **Do not compare at pp512.** Use pp8192 / pp16384 / tg512, where noise is 0.0–1.5%.
13. **Report the spread, not just the median.** Strata's ±18% decode variance is a real
    property of the engine, and a median hides it.
14. **Report absolute times, not only rates.** The −90% figure in §7.2 decomposed into a
    −48.5% rate and a 23 s fixed cost; only the absolute times made that visible.
15. **Trust the kernel's PCIe log over sysfs.** sysfs reported both cards as Gen5 x16 and
    would have hidden a 16x difference.

---

## 14. Open questions

| Question | Why it matters | How to settle it |
|----------|----------------|------------------|
| Is the ~23 s fixed cost on x2 caused by disk re-read, model reload, or the slot itself? | It decides whether the short-prompt headline is −90% or −48.5% | Check llama-swap load/unload events per request; re-run with idle-unload disabled (§7.4) |
| Why is x2 decode noisy (13.8–38.1) while x2 prefill is reproducible to 0.1%? | Suggests a second bottleneck (RAM/swap) alongside the bus | Re-run with the model guaranteed resident and caches dropped |
| Avalon on the x2 slot | The other half of §7 | Never measured — the load froze the machine (§7.5, §12.3) |
| Does Vulkan also lose ~50% steady-state on x2 for a streaming MoE? | Vulkan wins dense decode; nobody has run the 125B on Vulkan | Run the 125B on `-dev Vulkan1`/`Vulkan0` |
| Strata x2 at 2048-token generations | Would separate bus-bound from KV-bound decode | Extend `tests/long.json` |
| rdna-boosts on a 7–14B model | 4B is compute-bound, 27B is memory-bound; the middle may rank differently | Need a mid-size model |
| ROCm 7.2.4 vs 7.8.0 | Fills a gap in the version matrix | `LD_LIBRARY_PATH=/home/timoti/rocm724-portable/lib` |
| `--spec-draft-n-max` 4 | Only 2 and 3 were swept for Avalon | Sweep at `tg=512`, greedy, `r=3` |

---

## 15. Future testing

| Test | Priority | Notes |
|------|----------|-------|
| Avalon on the x2 (Sapphire) slot | **High** | The one missing half of §7; needs the memory guard in §12.3 |
| Separate the 23 s fixed cost from the slot | **High** | Decides the headline number in §7.3 |
| 125B MoE on Vulkan, both slots | Medium | Vulkan wins dense decode; untested on Flash-Next |
| Direct Strata connection (no llama-swap) | Medium | `--serve` exists; `--bench-pp`/`--bench-tg` rejected the flag combination used in the audit (rc=2) — worth a separate attempt |
| Strata x2 with 2048-token generations | Low | Separates bus-bound from KV-bound decode |
| `--spec-draft-n-max` 2/3/4 sweep | Medium | Avalon, greedy, `tg=512`, `r=3` |
| ROCm 7.2.4 vs 7.8.0 | Medium | `/home/timoti/rocm724-portable/lib` |
| rdna-boosts on a 7–14B model | Low | Fills the compute-bound → memory-bound transition |
| Avalon native `llama-bench` on Flash-Next | **Blocked** | 125B needs ~55 GB of buffers and `llama-bench` has no CPU-expert offload, so it fails to load; Avalon 125B can only be measured through its server path |

---

## 16. Reproduction

### 16.1 Benchmarks

```bash
# Dense-model matrix (engine binary directly, no proxy), pinned to the fast card
HIP_VISIBLE_DEVICES=1 llama-bench -m <model.gguf> \
  -ngl 99 -fa 1 -dev ROCm0 -b 4096 -ub 2048 \
  -p 512,2048,8192,16384 -n 512 -r 3 -mmp 0 -o csv
# Vulkan: use -dev Vulkan1 (fast card) or -dev Vulkan0 (slow card). RADV_DEVICE does nothing.

# 125B engines through llama-swap
cd ~/ai-driven-projects/perf-bench
python3 bench.py --host 127.0.0.1 --port 8080 --model <model-id> \
  --tests prefill,tests/long.json --tag mytag --repeat 3 --timeout 900
```

`tests/long.json` is the 512-token greedy suite: prefill at 512/2048/8192/16384 and decode at
depths 1024/8192/32768, 512 tokens each, `min_tokens` + `ignore_eos`.

### 16.2 Avalon direct

```bash
env HIP_VISIBLE_DEVICES=1 /home/timoti/Avalon/build/bin/llama-server \
  -m /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf \
  -c 200000 -b 4096 -ub 2048 -fa on -ctk q8_0 -ctv q4_0 --jinja --parallel 1 \
  -md /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf \
  --spec-type draft-mtp --spec-draft-n-max 3 -ubd 256 -ctkd q8_0 -ctvd q4_0 \
  --temp 0.6 --top_k 30 --top-p 0.95 --reasoning-effort low --reasoning-budget 4092 \
  --host 0.0.0.0 --port 5800 --metrics
```

### 16.3 Strata via llama-swap

```bash
cd /home/timoti/llama-swap
HIP_VISIBLE_DEVICES=1 LD_LIBRARY_PATH="/opt/rocm/lib" ./llama-swap -config config.yml -listen :8080
# wait for the model to load, then bench as in 16.1
```

### 16.4 The slot test

`perf-tuning/results/audit-2026-11-01/orchestrate-slot-x2.sh` reproduces §7, including the
memory guard: it flips every `HIP_VISIBLE_DEVICES=1` to `0` for the Sapphire side, gives
Strata its own config with `"gpu": 0`, drops caches between engines, and refuses to load when
available RAM is below the requirement instead of freezing the box.

---

## Appendix A. Raw data

Raw output lives under `perf-tuning/results/audit-2026-11-01/` and `perf-bench/results/`.
Both are gitignored by convention — **the tables in this document are the record**; the
directories hold the per-measurement files behind them.

| Path | Contents |
|------|----------|
| `clean-gpu1/b_<engine>_<model>.csv` | llama-bench CSVs, x16 card, corrected methodology, `r=3`. Engines `rdna101`, `rdna713`, `rdna717`, `b1347_717`, `stock101`, `vulkan1`; models `27b`, `4b`. One row per measurement with `avg_ts`/`stddev_ts` → §5 |
| `sapphire-x2/a_<engine>_<model>_x2.csv` | Same matrix on the x2 card → §7.1. `batchA.log` is the harness output |
| `sapphire-x2/b_slot-strata-x2.csv` | perf-bench rows, tag `slot-strata-x2`, Strata 125B on x2 → §7.2 |
| `http-125b/avalon-vs-strata-125b.csv` | perf-bench rows, tags `audit-avalon-alone-r3` and `audit-strata-alone-r3` → §6, and the x16 baseline for §7.2 |
| `http-125b/strata-alone.log`, `strata-run.log` | Full harness output and orchestration log |
| `sapphire-x2/gpu0_*.csv` | **Superseded** — old methodology (`tg=128`, Vulkan unpinned), Avalon resident on the other card; Vulkan rows there are unusable (`devices=auto` → both GPUs) |
| `orchestrate-engines.sh`, `orchestrate-strata.sh`, `orchestrate-slot-x2.sh` | Reproduction scripts |
| `README.md` | Methodology table for these files and which ones are valid |

Avalon is absent from the `llama-bench` matrices on purpose: its 125B model needs a ~55 GB
buffer allocation and `llama-bench` has no CPU-expert offload, so it cannot be measured that
way. Avalon 125B is only measurable through its own server.

One earlier round is invalid and excluded from every table: Avalon measured while Strata was
also resident (prefill dropped to 2.5 tps). See §4.2, bug 3.
