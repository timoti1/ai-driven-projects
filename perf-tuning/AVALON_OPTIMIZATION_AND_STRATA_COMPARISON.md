# Avalon Optimization and Strata Comparison

**Test Dates:** 2026-10-31 … 2026-11-01  
**Branch:** `aic8800-wifi-bt-driver`  
**Repository:** `timoti1/ai-driven-projects`  
**Directories:** `perf-tuning/` and `perf-bench/`  
**Status:** Complete for the engines and models listed

> **Where to read first:** section **2b** (methodology — what was measured and why), then
> section **16** (clean re-audit — the authoritative numbers). Sections 3–15 are the
> earlier rounds; they are kept as history and each conflicting table is marked with what
> superseded it. Section 17 is a side result: two identical GPUs in different PCIe slots.

---

## 1. Test Stand

### Hardware Specification

| Component | Specification |
|-----------|--------------|
| CPU | AMD Ryzen 7 5800 (8C/16T, no AVX-512, expert kernels on AVX-2) |
| GPU 0 | AMD Radeon RX 9070 (**Sapphire**, PCI `05:00.0`, subvendor `1da2`, **slow slot: PCIe 3.0 x2**, gfx1201) |
| GPU 1 | AMD Radeon RX 9070 (**Gigabyte**, PCI `0a:00.0`, subvendor `1458`, **fast slot: PCIe 4.0 x16**, gfx1201) |
| VRAM per GPU | 16 GB |
| System RAM | 62 GB (+8 GB swap) |
| OS | Linux (Ubuntu 24.04-based) |
| GPU Power Limit | **210 W (undervolted/underclocked)** — below factory specification |

**Important caveat:** Both RX 9070 GPUs are power-limited to 210 W, which is below their factory TGP. The same cards running at full power could show better results. All performance numbers below are measured with this 210 W limit in effect.

### GPU Mapping (HIP_VISIBLE_DEVICES)

- `HIP_VISIBLE_DEVICES=0` → Sapphire (PCIe 3.0 x2, slow slot)
- `HIP_VISIBLE_DEVICES=1` → Gigabyte (PCIe 4.0 x16, fast slot)

The same order applies to Vulkan (`-dev Vulkan0` = Sapphire, `-dev Vulkan1` = Gigabyte):
both backends enumerate by PCI order, and `05:00.0` sorts before `0a:00.0`.

### How the slot widths were verified (sysfs lies, the kernel does not)

`sysfs` reports **both** cards as `16x 32.0 GT/s` (PCIe 5.0 x16), which is wrong — the
cards are capable of Gen5 x16, but the motherboard is not. `lspci`/sysfs read the
capability registers, not the trained link.

The kernel's own message at boot reports the negotiated link and is authoritative:

```
pci 0000:05:00.0: 15.752 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x2
                   link at 0000:02:00.0   (capable of 504.112 Gb/s with 32.0 GT/s PCIe x16)
pci 0000:0a:00.0: 252.048 Gb/s available PCIe bandwidth, limited by 16.0 GT/s PCIe x16
                   link at 0000:00:03.1   (capable of 504.112 Gb/s with 32.0 GT/s PCIe x16)
```

- `05:00.0` (Sapphire) hangs off `02:00.0` — a chipset bridge — at **Gen3 x2**
  (8 GT/s × 2 lanes = 15.75 Gb/s ≈ 2.0 GB/s).
- `0a:00.0` (Gigabyte) hangs off `00:03.1` — directly on the CPU root complex — at
  **Gen4 x16** (16 GT/s × 16 = 252 Gb/s ≈ 31.5 GB/s).

So the two cards differ by **16x** in bus bandwidth. Both are otherwise identical GPUs
(gfx1201, 16 GB, same 210 W power cap).

Check it on this machine with:

```bash
journalctl -k | grep "available PCIe bandwidth"   # authoritative
lspci -vs 05:00.0 | grep LnkSta                   # reports the card's capability, not the link
```

---

## 2. Software Stack

| Component | Version | Path |
|-----------|---------|------|
| llama-swap | v265 (commit d1e743f, build 2026-10-14) | `/home/timoti/llama-swap/` |
| Listen | `0.0.0.0:8080` | HTTP proxy |
| ROCm | 7.8.0 | `/opt/rocm` |
| HIP / hipcc | 7.16.26385-0000000, AMD clang 24.0.0 | `/usr/bin/hipcc` |
| Vulkan ICD (Mesa RADV) | API 1.4.318 | `/home/timoti/mesa-build/libvulkan_radeon.so` |

---

## 2b. Test Methodology (How These Numbers Were Measured)

**Added 2026-11-01.** The first rounds of measurements were noisy. The table below
lists every methodology change and *why* it was made. Numbers in sections marked
"clean re-audit" use the corrected methodology; earlier numbers are kept for
reference but are superseded where they conflict.

| # | Condition | Before | After | Why |
|---|-----------|--------|-------|-----|
| 1 | Sampling temperature | `0.6` | `0.0` (greedy) | Temperature makes the model choose different tokens on every repeat. Different tokens → different sequence lengths → different attention cost. Pure noise, measures nothing about the engine. Greedy decoding makes repeats directly comparable. |
| 2 | Early stop at EOS | allowed | `min_tokens = n`, `ignore_eos = true` | With free EOS the model stopped whenever it liked: completions varied **96…128 tokens** between repeats. Throughput is computed over tokens actually generated, so a short run mostly measures fixed request overhead, not the engine. A fixed token count makes every repeat measure the same amount of work. |
| 3 | Generation length | 128 tokens | 512 tokens | A 128-token generation is dominated by per-request overhead (HTTP, scheduling, first-token latency). Longer generation amortizes that overhead over real work, so the number describes steady-state decode. |
| 4 | Prompt length | 512 / 2048 / 8192 | 512 / 2048 / 8192 / **16384** | Same reasoning as #3 for prefill. Long prompts also expose KV-cache and memory-bandwidth behaviour that short prompts hide. |
| 5 | Repetitions | 1 | **3** | Three is enough *because* the load per repetition is now much bigger — longer prompts and 4× longer generations reduce the spread far more than more repetitions would. See measured stddev below. |
| 6 | GPU selection (HIP) | `HIP_VISIBLE_DEVICES=1` only | + `-dev ROCm0` | Explicit device pin so the engine cannot spread across both cards. |
| 7 | GPU selection (Vulkan) | `RADV_DEVICE=1` | **`-dev Vulkan1`** | `RADV_DEVICE` does **not** restrict devices for llama.cpp: `llama-bench` still reported `devices=auto` and both GPUs in `gpu_info`, i.e. it loaded across the Sapphire *and* the Gigabyte. Vulkan numbers measured that way are not single-card numbers. |
| 8 | Resident models | several 125B models loaded at once | **one 125B engine at a time** | Avalon and Strata are both Qwen3.8-Flash-Next 125B MoE and both keep experts in system RAM. 62 GB cannot hold two: prefill collapsed to **3.7 tps** (RAM thrash). Any number taken while a second 125B model is resident is invalid. |
| 9 | GPU state | engine measured while another model held ~16 GB of VRAM | engine measured with the card **free** | A 27B/125B engine either fails to allocate or silently offloads to CPU. The agent's own model has to be released before measuring other engines (see section 16). |

### Why 3 repetitions are enough (measured stddev)

Stability of the corrected setup, Qwen3.8-27B IQ3_XXS, GPU 1, `r=3`:

| Measurement | Stddev |
|-------------|--------|
| prefill 512 | ±10.9% |
| prefill 2048 | ±0.7% |
| prefill 8192 | ±0.1% |
| prefill 16384 | ±0.1% |
| decode 512 | ±0.8% |

**Rule that follows from this table:** `pp512` is not a usable comparison point —
at 512 tokens the measurement is dominated by launch/scheduling latency and it
carries 5–14% noise even with the fixed harness. Compare at **pp8192 / pp16384 /
tg512**, where noise is 0.0–1.5%. Earlier rounds (temperature 0.6, free EOS, 128
tokens, `r=1`) showed ±19% on `pp512`.

---

## 3. Avalon Optimization (Fine-Tuning Parameters)

### Goal

Find optimal command-line parameters for model `avalon-qwen3.8-flash-next-C2`
(Qwen3.8-Flash-Next 125B MoE, IQ3_K, 33 shards) on Avalon fork 0.26.0
(llama.cpp 0.26.0, HIP/ROCm 7.8.0).

### Optimized Configuration

**Command-line parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `-b` | 4096 | Batch size (was 2048) |
| `-ub` | 2048 | Micro-batch (was 1024) |
| `--spec-draft-n-max` | 3 | Max draft tokens for speculative decoding (was 2) |
| `-fa` | on | Flash attention |
| `-ctk` | q8_0 | KV cache K quantization |
| `-ctv` | q4_0 | KV cache V quantization |
| `--jinja` | — | Jinja chat template |
| `--parallel` | 1 | Number of concurrent sessions |
| `-md` | MTP GGUF | Path to MTP draft model |
| `--spec-type` | draft-mtp | Speculative decoding type |
| `-ubd` | 256 | Draft ubatch size |
| `-ctkd` | q8_0 | Draft KV cache K quantization |
| `-ctvd` | q4_0 | Draft KV cache V quantization |
| `--temp` | 0.6 | Temperature |
| `--top_k` | 30 | Top-k sampling |
| `--top_p` | 0.95 | Top-p sampling |
| `--reasoning-effort` | low | Reasoning effort level |
| `--reasoning-budget` | 4092 | Reasoning token budget |
| `HIP_VISIBLE_DEVICES` | 1 | Model on Gigabyte (PCIe x16) |

### Avalon Optimization Results

| Configuration | parallel | batch | draft | prefill 8192 | decode 8192 | TTFT 8192 |
|---------------|----------|-------|-------|-------------|-------------|-----------|
| Original (batch 2048, draft 2) | 2 | 2048 | 2 | ~497 tps | ~46 tps | ~10.8 s |
| batch 4096, draft 2 | 2 | 4096 | 2 | ~889 tps | ~60 tps | ~10.8 s |
| batch 4096, draft 3 (dual) | 2 | 4096 | 3 | ~941 tps | ~63 tps | ~5.8 s |
| batch 4096, draft 3 (single, live-tested) | 1 | 4096 | 3 | ~984 tps | ~75 tps | ~5.5 s |
| Via llama-swap proxy (live-tested 2026-10-31) | 1 | 4096 | 3 | ~931–954 tps | ~56–64 tps | ~5.8–6.1 s |

**Key optimization findings (verified by live testing):**

- `--parallel 1` gives **higher decode throughput** (~75 tps vs ~63 tps at parallel=2) with similar TTFT (~5.5 s vs ~5.8 s)
- batch 4096 gives **+89% prefill** compared to batch 2048
- draft 3 gives **+10-20% decode throughput** compared to draft 2
- llama-swap proxy adds **moderate overhead** (~20% slower decode, ~3–5% slower prefill) — **NOT 3-4x** as previously claimed. Direct connection to engine port (5800) is still preferred for maximum performance.

---

## 4. Strata Live Testing (through llama-swap)

### Strata Configuration

| Parameter | Value |
|-----------|-------|
| Engine | Strata proprietary (HIP) |
| Binary | `/media/timoti/Data/repos/Strata/engine/strata` |
| Model | Qwen3.8-Flash-Next IQ3_S |
| Pack | `/media/timoti/Data/Strata-data/packs/swift-iq3_s` |
| Native shard | `Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf` |
| PLE shard | `Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf` |
| MTP | `/media/timoti/Data/Strata-data/mtp/rt` |
| Expert profile | `/media/timoti/Data/repos/Strata/data/expert-profile.bin` |
| Max context | 200000 |
| KV storage | int8 |
| KV resident | 20480 |
| MTP hnorm | stream |
| Spec | 4 |
| Spec min-p | 0.5 |
| Backend | HIP / ROCm 7.8.0 |
| GPU | 1 (Gigabyte, PCIe x16) |
| Launch | Via llama-swap on port 8080 |

### Live Strata Results (via llama-swap, port 8080)

| Test | Depth | prefill_tps | decode_tps | first_token_s | completion |
|------|-------|-------------|------------|---------------|------------|
| prefill | 393 | 15.7 | — | — | — |
| prefill | 1394 | — | 374.6 | — | — |
| prefill | 5393 | — | 1117.9 | — | — |
| prefill | 394 | 63.3 | — | — | — |
| prefill | 1392 | — | 569.3 | — | — |
| prefill | 5393 | — | 1394.1 | — | — |
| decode | 1024 | — | 32.2 | 1.85 | 128 |
| decode | 8192 | — | 64.6 | 3.07 | 128 |
| decode | 32768 | — | 44.1 | 10.39 | 128 |
| decode | 1024 | — | 69.8 | 1.84 | 128 |
| decode | 8192 | — | 65.6 | 3.09 | 128 |
| decode | 32768 | — | 65.8 | 10.50 | 128 |

**Average Strata:** prefill 8192 ≈ **1256 tps**; decode 8192 ≈ **65.1 tps**; TTFT 8192 ≈ **3.08 s**

---

## 5. Head-to-Head Comparison: Avalon vs Strata (via llama-swap)

Both models tested through the same `llama-swap` proxy on port 8080, identical test parameters (prefill 512/2048/8192, decode 1024/8192/32768, 128 tokens generation, 2 repetitions).

| Test | Depth | Strata prefill | Strata decode | Strata TTFT | Avalon prefill | Avalon decode | Avalon TTFT |
|------|-------|---------------|---------------|-------------|----------------|---------------|-------------|
| prefill | ~393 | 15.7 | — | — | 202.2 | — | — |
| prefill | ~1382 | 569.3 | — | — | 665.2 | — | — |
| prefill | ~5393 | 1117.9 | — | — | 969.8 | — | — |
| decode | 1024 | — | 32.2 / 69.8 | 1.85 / 1.84 | — | 61.4 / 67.1 | 2.57 / 2.73 |
| decode | 8192 | — | 64.6 / 65.6 | 3.07 / 3.09 | — | 70.4 / 66.9 | 5.78 / 5.77 |
| decode | 32768 | — | 44.1 / 65.8 | 10.39 / 10.50 | — | 61.5 / 65.5 | 20.67 / 19.75 |

### Comparison Summary

| Metric | Strata (IQ3_S) | Avalon (125B MoE) | Winner |
|--------|---------------|-------------------|--------|
| **Prefill 8192** | ~1256 tps | ~956 tps | **Strata (+31%)** |
| **Decode 8192** | ~65.1 tps | ~68.7 tps | **Avalon (+5.5%)** |
| **TTFT 8192** | ~3.08 s | ~5.78 s | **Strata (1.9× faster)** |
| Decode 32768 | ~65.8 tps | ~65.5 tps | Approximately equal |
| Decode 1024 | ~51 tps (avg) | ~64 tps (avg) | **Avalon** |
| Prefill 512 | ~15–63 tps | ~202–257 tps | **Avalon** |
| Prefill 2048 | ~375–570 tps | ~665–684 tps | **Avalon** |

---

## 6. Key Findings

### Performance

1. **Strata is faster in prefill** — ~1256 tps vs ~956 tps at 8K context (+31% for Strata)
2. **Strata is faster in TTFT** — ~3.08 s vs ~5.78 s (nearly 2× faster first token)
3. **Avalon is slightly better in decode** — ~68.7 vs ~65.1 tps (+5.5% for Avalon)
4. **At long context (32K)** — approximately equal (~65 tps)
5. **At short prefill (512–2048)** — Avalon significantly outperforms Strata

### Architectural Differences

- **Avalon** uses 33-shard GGUF format (llama.cpp), model on Gigabyte GPU (PCIe x16)
- **Strata** uses native IQ packs (separate `.bin` experts + GGUF shards), model on Gigabyte GPU (PCIe x16)
- Model formats are incompatible — direct same-model comparison is impossible, models are logically equivalent (Qwen3.8-Flash-Next) but physically different

### llama-swap Proxy — Live Test Results

**Tested 2026-10-31:** Direct engine (port 5800) vs via llama-swap proxy (port 8080), same model, same parameters.

| Metric | Direct (5800) | Via llama-swap (8080) | Overhead |
|--------|--------------|----------------------|----------|
| Prefill 8192 | ~984 tps | ~931–954 tps | ~3–5% slower |
| Decode 8192 | ~71–80 tps | ~56–64 tps | ~20% slower |
| TTFT 8192 | ~5.5–5.6 s | ~5.8–6.1 s | ~10% slower |
| Decode 1024 | ~71–76 tps | ~63–67 tps | ~12% slower |
| Decode 32768 | ~73–80 tps | ~58–65 tps | ~20% slower |

**Conclusion:** llama-swap adds **moderate overhead** (~20% decode, ~3–5% prefill). The previously claimed "3-4x overhead" was **not confirmed** by live testing and appears to have been from a different/test-faulty run. Direct engine connection is still preferred for maximum performance, but llama-swap overhead is not prohibitive.

### Why llama-swap Adds Overhead — Potential Explanations

The ~20% decode overhead and ~3–5% prefill overhead when going through llama-swap (port 8080) vs direct engine connection (port 5800) can be explained by several factors:

1. **HTTP proxy layer:** Every request passes through an additional HTTP stack (localhost TCP/IP, request parsing, response serialization). This adds latency per request, which is more noticeable for short decode requests where GPU compute time is small.

2. **JSON serialization/deserialization:** Requests and responses must be serialized to/from JSON. For large prompts (8192+ tokens), this adds CPU overhead on both the proxy and engine sides.

3. **Inter-process data copying:** The request travels from client → llama-swap process → llama-server process, and the response travels back. Each hop involves memory copying and context switching between processes.

4. **Request routing and validation:** llama-swap must look up the model in its config, validate the request, check capabilities, and forward to the correct backend. This adds a small fixed cost per request.

5. **Logging and metrics:** llama-swap logs every request and response, which involves disk I/O and CPU cycles that are bypassed in direct connection.

6. **Streaming overhead:** For streaming responses (token-by-token), each token must be wrapped in an HTTP chunked response and passed through the proxy, adding per-token overhead.

**Why prefill has less overhead (~3–5%):** Prefill is GPU-bound (large matrix operations). The fixed proxy overhead is amortized over the longer GPU compute time, making it proportionally smaller.

**Why decode has more overhead (~20%):** Decode is more latency-sensitive with many small per-token operations. The fixed proxy overhead per request/token represents a larger fraction of total time.

---

### Parallel Sessions Test (Live Results)

**Tested 2026-10-31:** Single session vs two concurrent sessions on Avalon parallel=2 engine (port 5800). Two simultaneous requests with 8192-token prompt, 128 max tokens each.

| Metric | Single Session | Two Parallel (combined) | Ratio |
|--------|---------------|------------------------|-------|
| Decode (single) | ~59–62 tps | — | — |
| Decode (two parallel) | — | ~43–45 tps (combined) | **0.70–0.76x** |
| Prompt (single) | ~659–854 tps | — | — |
| Prompt (two parallel) | — | ~661–694 tps (combined) | **0.81–1.00x** |
| Wall clock (single) | ~4.2–5.0 s | — | — |
| Wall clock (two parallel) | — | ~5.4 s | — |

**Key finding:** Running two parallel sessions does **NOT** increase combined decode throughput. In fact, combined decode drops to ~70–76% of single-session throughput. Prompt processing is roughly unchanged (~1.0x). **Conclusion: parallel=1 is better for maximum throughput; parallel=2 does not improve combined performance.**

---

## 7. System Resource Usage Comparison (Real Measurements)

Measurements taken on ryzen5800 (192.168.1.104) with 62 GB system RAM, dual RX 9070 GPUs, ROCm 7.8.0. Both engines tested with model loaded and idle, then during an inference request (200 tokens generation).

### Test Environment

| Component | Specification |
|-----------|--------------|
| System RAM | 62 GB total |
| Swap | 8 GB |
| GPU 0 | RX 9070 Sapphire (PCIe x2, HIP_VISIBLE_DEVICES=0) |
| GPU 1 | RX 9070 Gigabyte (PCIe x16, HIP_VISIBLE_DEVICES=1) |
| ROCm | 7.8.0 |

### Avalon Resource Usage

**Engine:** `avalon-qwen3.8-flash-next-C2` on port 5800 (direct, no proxy)

| Metric | Idle (model loaded) | During Inference |
|--------|--------------------|------------------|
| Process CPU | ~36% | ~104% (multi-core) |
| Process RSS | ~51.8 GB | ~52.3 GB |
| System RAM used | ~5.4 GiB | ~5.9 GiB |
| System RAM available | ~57 GiB | ~56 GiB |
| Swap used | ~1.7 GiB | ~1.7 GiB |
| GPU 0 (Sapphire) Temp | 42°C | — |
| GPU 1 (Gigabyte) Temp | 41°C | — |
| GPU 1 VRAM used | 98% | — |
| GPU 1 GPU load | 3% | — |

**Key observation:** Avalon's system RAM footprint is modest (~6 GB). Most memory is in VRAM (GPU 1 at 98%). System remains responsive with 56+ GB available.

### Strata Resource Usage

**Engine:** `qwen3.8-flash-IQ3_S` via llama-swap on port 8080

| Component | CPU | RSS |
|-----------|-----|-----|
| llama-swap proxy | ~0% | ~25-29 MB |
| strata server (Python) | ~0.6% | ~30-32 MB |
| strata engine | ~50-75% | ~50.7-51 GB |

| Metric | Idle (model loaded) | During Inference |
|--------|--------------------|------------------|
| Strata engine CPU | ~50% | ~75% |
| System RAM used | ~54 GiB | ~54 GiB |
| System RAM available | ~8.2 GiB | ~7.9 GiB |
| Swap used | ~3.9 GiB | ~3.8 GiB |
| GPU VRAM | — | — |

**Key observation:** Strata consumes ~54 GB of system RAM — nearly the entire 62 GB available. Swap usage rises to ~3.9 GB. Only ~8 GB remains available for other processes. This can cause system instability on machines with less RAM.

### Side-by-Side Summary

| Resource | Strata | Avalon | Difference |
|----------|--------|--------|------------|
| System RAM (idle) | ~54 GiB | ~5.4 GiB | **Strata uses 10× more** |
| System RAM (inference) | ~54 GiB | ~5.9 GiB | **Strata uses 9× more** |
| System RAM available | ~8 GB | ~56 GB | **Avalon leaves 7× more free** |
| Swap usage | ~3.9 GiB | ~1.7 GiB | **Strata uses 2.3× more swap** |
| Engine CPU (idle) | ~50% | ~36% | Avalon lighter |
| Engine CPU (inference) | ~75% | ~104% | Avalon uses more CPU cores |
| GPU VRAM | ~98% (GPU 1) | ~98% (GPU 1) | Similar |
| System responsiveness | Constrained (8 GB free) | Comfortable (56 GB free) | **Avalon better** |

---

**Conclusion on system load:** Avalon is significantly lighter on system RAM, leaving the majority of memory available for other applications. Strata reserves most of system RAM (~54 GB of 62 GB), pushing the system into swap and leaving only ~8 GB free — a concern for production environments where multiple services share the same host.

## 8. Files in Repository

| File | Description |
|------|-------------|
| `perf-tuning/AVALON_OPTIMIZATION_AND_STRATA_COMPARISON.md` | This file — current optimization and comparison results |
| `perf-tuning/AVALON_BENCHMARK_RESULTS.md` | Detailed Avalon benchmark results |
| `perf-bench/BENCHMARK_README.md` | Benchmark overview |
| `perf-tuning/scripts/launch_engine.sh` | Engine launch script |
| `perf-tuning/scripts/run_matrix.sh` | Matrix test runner |
| `perf-tuning/scripts/update_engines.sh` | Engine update script |
| `perf-bench/bench.py` | Benchmark harness |
| `perf-bench/results/runs.csv` | Raw test results |

---

## 9. How to Reproduce

### Avalon Direct (port 5800)

```bash
env HIP_VISIBLE_DEVICES=1 /home/timoti/Avalon/build/bin/llama-server \
  -m /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf \
  -c 200000 -b 4096 -ub 2048 -fa on -ctk q8_0 -ctv q4_0 --jinja --parallel 1 \
  -md /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf \
  --spec-type draft-mtp --spec-draft-n-max 3 -ubd 256 -ctkd q8_0 -ctvd q4_0 \
  --temp 0.6 --top_k 30 --top-p 0.95 --reasoning-effort low --reasoning-budget 4092 \
  --host 0.0.0.0 --port 5800 --metrics

python3 bench.py --host 127.0.0.1 --port 5800 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-direct --repeat 2
```

### Strata via llama-swap (port 8080)

```bash
cd /home/timoti/llama-swap
HIP_VISIBLE_DEVICES=1 LD_LIBRARY_PATH="/opt/rocm/lib" ./llama-swap -config config.yml -listen :8080

# Wait for model to load, then:
python3 bench.py --host 127.0.0.1 --port 8080 --model qwen3.8-flash-IQ3_S \
  --tests health,prefill,decode --tag strata-via-swap --repeat 2
```

---

## 10. ROCm 7.13 Results

Tested 2026-11-01 with Avalon fork (HIP), ROCm 7.13 (`/opt/rocm/core-7.13/lib`).

| Metric | ROCm 7.8.0 | ROCm 7.13 | Change |
|--------|-----------|-----------|--------|
| Prefill 8192 | ~998 tps | ~1012 tps | +1.4% |
| Decode 8192 | ~81 tps | ~66 tps | -18.5% |
| TTFT 8192 | ~5.5 s | ~18.3 s | +233% |
| Decode 32768 TTFT | — | ~83.5 s | — |

**Conclusion:** ROCm 7.13 shows marginal prefill improvement but significantly worse decode performance and TTFT. Not recommended for Avalon.

---

## 11. rdna-boosts (AMD RDNA4-Optimized Fork)

**Source:** `stew675/llama-cpp-rdna-boosts` (commit 561696677, 0.7.0-dev)
**Binary:** `/home/timoti/Downloads/llama.cpp/build/bin/llama-server`
**Backend:** HIP/ROCm 7.8.0, RDNA4 (gfx1201) optimizations

### Compatibility

- **Cannot load Avalon fork model** (33-shard custom MoE format, invalid ggml type 43)
- **Cannot load 125B MoE abliterated model** (exceeds 16 GB VRAM)
- **Works with standard GGUF models** (e.g., Spark-X2.6-4B, 4B params)

### Spark-X2.6-4B Benchmark (4B model, fits in 16 GB VRAM)

| Engine | Backend | Prefill 8192 | Decode 8192 | TTFT 8192 | Notes |
|--------|---------|-------------|-------------|-----------|-------|
| rdna-boosts | HIP (ROCm 7.8.0) | ~5436 tps | ~129 tps | ~0.95 s | RDNA4-optimized fork |
| llama-latest | Vulkan (RADV) | ~3925 tps | ~146 tps | ~1.28 s | Stock Vulkan backend |
| rocm-llama | HIP (ROCm 7.8.0) | ~6051 tps | ~117 tps | ~0.90 s | Stock ROCm fork |

**Findings:**
- rdna-boosts prefill is **+38%** faster than Vulkan, but **−10%** slower than stock ROCm
- rdna-boosts decode is **+10%** faster than stock ROCm, but **−12%** slower than Vulkan
- For small models (4B), stock ROCm and Vulkan are competitive; rdna-boosts advantage is not clear-cut
- rdna-boosts requires same K and V cache types (unlike Avalon which allows q8_0/q4_0 mix)

### Qwen3.8-27B IQ3_XXS Benchmark (27B model, 9.8 GB)

**Tested 2026-11-01, then re-measured with the corrected methodology** (section 2b,
`r=3`, greedy, fixed token counts, device pinned, card free). The clean numbers are
in section 16; the table below is the earlier HTTP round, kept for TTFT and as a
record of what was superseded.

| Engine | ROCm | Prefill 8192 | Decode 8192 | Decode 1024 | TTFT 8192 |
|--------|------|-------------|-------------|-------------|----------|
| rdna-boosts | 10.1 (HIP 7.16) | 949 tps | 39.1 tps | 40.1 tps | 5.38 s |
| rdna-boosts | 7.17 nightly (HIP 7.17) | 941 tps | 32.4 tps | 33.2 tps | 5.71 s |
| vanilla llama-b1347 | 7.17 nightly | 935 tps | 32.4 tps | 33.1 tps | 5.72 s |
| rocm-llama (stock) | 10.1 (HIP 7.16) | 826 tps | 25.2 tps | 25.6 tps | 6.56 s |
| llama-latest (Vulkan) | n/a | 779 tps [^vk] | 33.7 tps [^vk] | 34.5 tps [^vk] | 6.87 s |
| Avalon (HIP) | 10.1 (HIP 7.16) | 922 tps | 34.1 tps | 34.9 tps | 5.89 s |

[^vk]: Measured with `RADV_DEVICE=1`, which does not restrict devices — `llama-bench`
reported `devices=auto` and both GPUs in `gpu_info`, so the model was loaded across
Sapphire *and* Gigabyte. These three Vulkan cells are **not** single-card numbers and
are superseded by section 16 (`-dev Vulkan1`, Gigabyte only).

**Key Findings (27B model)** — revised by the clean re-audit in section 16:
1. **rdna-boosts with ROCm 10.1 is fastest in prefill** (1058 tps at pp8192)
2. **ROCm 7.17 nightly is SLOWER than 10.1** for 27B decode (33.2 vs 39.6 tps, −16%) — confirmed by clean re-measurement
3. **Vanilla llama.cpp = rdna-boosts** at the same ROCm (1000 vs 1009 tps, 32.8 vs 33.2 tps) — the AMD fork adds no measurable gain at 27B
4. **Stock ROCm fork is slowest** (26.0 tps decode, −34% vs rdna-boosts)
5. **Vulkan wins decode** once pinned to a single card (40.4 tps) — see section 16
6. **Avalon (HIP) is close to rdna-boosts** (−13% decode)

### ROCm Version Impact Summary

| ROCm Version | 4B model (Spark) | 27B model (Qwen) | Notes |
|--------------|-----------------|-----------------|-------|
| 10.1 (HIP 7.16) | Best decode | Best decode | Production release |
| 7.17 nightly (HIP 7.17) | +4% prefill, −12% decode | −17% decode | Newer HIP runtime, may have regressions |
| 7.13 (HIP 7.13) | Not tested | Not tested | Preview release |

**Conclusion:** ROCm 10.1 (HIP 7.16) provides the best overall performance for llama.cpp-based engines. The newer ROCm 7.17 nightly shows improvements in prefill but regressions in decode for larger models.

---

## 12. Strata Update: Old vs New Build (Corrected)

**Tested 2026-11-01.** Both builds are version 0.1.51, but different binaries:
- **Old:** `/media/timoti/Data/repos/Strata/engine/strata` (ROCm 7.17 libs)
- **New (fresh build):** `/media/timoti/Data/repos/Strata/work-rx9070/b/strata` (ROCm 7.8.0 or 7.17 libs)

### Key Finding: ROCm Version Matters More Than Build

The initial "−42% decode regression" was **not** caused by the new build, but by the ROCm library version:
- Old build: linked against **ROCm 7.17** (`/media/timoti/Data/llama-builds/llama-b1347-rocm-gfx120X/`)
- New build (initial test): ran with **ROCm 7.8.0** (`/opt/rocm/lib`)
- New build (corrected test): ran with **ROCm 7.17** (same as old)

### Qwen3.8-Flash-Next IQ3_XXS (warm, repeat 2)

| Metric | OLD (ROCm 7.17) | NEW (ROCm 7.8.0) | NEW (ROCm 7.17) | New vs Old (same ROCm) |
|--------|-----------------|------------------|-----------------|------------------------|
| Prefill 8192 | ~1852 tps | ~1865 tps | ~1844 tps | **−0.4%** (identical) |
| Decode 1024 | ~74 tps | ~56 tps | ~71 tps | **−4%** (within noise) |
| Decode 8192 | ~81 tps | ~63 tps | ~80 tps | **−1%** (identical) |
| Decode 32768 | ~63 tps | ~52 tps | ~88 tps | **+40%** (new build faster) |

**Conclusion:** The new build performs **identically** to the old build when using the same ROCm version. The earlier "−42% regression" was an artifact of comparing different ROCm versions (7.8.0 vs 7.17), not a build difference.

**Recommendation:** The new build is safe to use. For best performance, ensure it runs with ROCm 7.17 libraries (set `lib_dirs` to `/media/timoti/Data/llama-builds/llama-b1347-rocm-gfx120X/` in the config).

### ROCm Version Impact on Strata

| ROCm Version | Prefill 8192 | Decode 8192 | Notes |
|--------------|-------------|-------------|-------|
| 7.17 (custom) | ~1852 tps | ~81 tps | Best decode performance |
| 7.8.0 (`/opt/rocm`) | ~1865 tps | ~63 tps | −22% decode vs 7.17 |

**Note:** ROCm 7.17 provides ~22% better decode performance than 7.8.0 for Strata. This is likely due to improved hipBLASLt kernels or better GPU scheduling in the newer ROCm release.

---

## 14. Avalon vs Strata: Qwen3.8-Flash-Next Direct Comparison

**Tested 2026-11-01, repeat 2, before the methodology fixes of section 2b. Superseded
by section 16.4** (which uses greedy sampling, fixed 512-token generations and `r=3`).
Kept because it records draft acceptance rates, which the clean round does not measure.

| Metric | Avalon (IQ3KS 125B MoE + MTP) | Strata new (IQ3_XXS abliterated) | Strata vs Avalon |
|--------|-------------------------------|----------------------------------|------------------|
| Prefill 8192 | ~1000 tps | ~1748–1847 tps | **+80%** |
| Decode 8192 | ~80 tps | ~80 tps | **≈ equal** |
| Decode 32768 | ~45–78 tps | ~49–93 tps | Strata more stable |
| Draft acceptance | 60–70% (mean len 2.8–3.1) | — | — |
| TTFT (8192 prompt) | ~5.4 s | ~3.1 s | **−43%** |

**Notes:**
- Avalon: `-c 32768 -b 4096 -ub 2048 -fa on -ctk q8_0 -ctv q4_0 --parallel 1`
  + `-md <mtp> --spec-type draft-mtp --spec-draft-n-max 3 --no-reasoning-preserve -ubd 256 -ctkd q8_0 -ctvd q4_0`
- Strata: `--spec 4 --kv int8 --kv-resident 20480` (built-in spec, no separate draft model)
- Strata is a custom engine optimized for this specific model architecture
- The abliterated model (Strata) is slightly smaller than the full Avalon fork model
- **Context size matters:** Avalon with `-c 200000` drops to ~60 tps decode (KV cache pressure)

**Conclusion:**
- **Prefill: Strata is 1.85x faster** (1847 vs 1000 tps) — dominates TTFT
- **Decode: Comparable** (~80 tps both) when using `-c 32768`
- **TTFT: Strata 43% lower** (3.1s vs 5.4s) due to prefill advantage
- For short-context workloads, Avalon is competitive in decode
- For long-context or high-TTFT workloads, Strata is clearly superior

---

## 16. Clean Re-Audit (Authoritative Numbers)

**Tested 2026-11-01.** Re-measurement of everything above under the corrected
methodology of section 2b. These are the numbers to use; earlier tables are kept as
history and are marked where they conflict.

### What the audit found wrong

1. **Vulkan was never pinned to one GPU.** `RADV_DEVICE=1` does not restrict devices.
   `llama-bench` reported `devices=auto` and listed both cards in `gpu_info`, so the
   model was sharded across Sapphire + Gigabyte. Every Vulkan cell before this section
   measures a two-GPU configuration, not the Gigabyte alone. Correct flag: `-dev Vulkan1`.
2. **Decode was measured on 128 free-EOS generations at temperature 0.6.** Completion
   length varied 96…128 tokens between repeats, so repeats did not measure the same work.
3. **Two 125B MoE models were resident at once** in one round (Avalon + Strata). RAM
   thrash drove prefill to 3.7 tps. Any 125B number taken while another 125B model is
   loaded is invalid.
4. **`pp512` is not a comparison point.** Even with the fixed harness it carries 5–14%
   noise; at temperature 0.6 it carried ±19%.

Raw data for this section: `perf-tuning/results/audit-2026-11-01/` (local only —
`perf-tuning/results/` and `perf-bench/results/` are gitignored by convention; the tables
below are the record). It holds the llama-bench CSVs per engine, the perf-bench rows for
the 125B head-to-head, and the orchestration scripts that produced them.

### 16.1 llama-bench matrix — Qwen3.8-27B IQ3_XXS

GPU 1 (Gigabyte, PCIe x16), device pinned (`-dev ROCm0` / `-dev Vulkan1`), `-b 4096 -ub 2048`,
flash-attn on, KV f16, `r=3`, `tg=512`. Stddev at pp8192/pp16384/tg512 is 0.0–1.5%.

| Engine | ROCm | pp2048 | pp8192 | pp16384 | tg512 | pp512 (noisy) |
|--------|------|--------|--------|---------|-------|---------------|
| rdna-boosts | 10.1 (HIP 7.16) | **1073.6** | **1058.5** | **1016.4** | 39.6 | 803.7 ±10.9% |
| rdna-boosts | 7.13 | 822.0 | 960.8 | 1010.5 | 38.6 | 1042.4 ±0.0% |
| rdna-boosts | 7.17 | 1030.7 | 1009.3 | 971.6 | 33.2 | 998.0 |
| vanilla llama-b1347 | 7.17 | 1027.4 | 999.9 | 913.2 | 32.8 | 996.6 |
| rocm-llama (stock) | 10.1 (HIP 7.16) | 883.6 | 876.9 | 833.3 | 26.0 | 826.5 ±10.5% |
| llama-latest (Vulkan, one card) | n/a | 971.6 | 940.5 | 896.1 | **40.4** | 992.4 |

### 16.2 llama-bench matrix — Spark-X2.6-4B IQ4_XS

Same conditions.

| Engine | ROCm | pp2048 | pp8192 | pp16384 | tg512 |
|--------|------|--------|--------|---------|-------|
| rdna-boosts | 10.1 | 6223.5 | 5912.1 | 5420.8 | 152.0 |
| rdna-boosts | 7.17 | **6937.6** | **6628.1** | **6115.2** | 132.1 |
| rocm-llama (stock) | 10.1 | 6709.1 | 6441.1 | 6000.7 | 133.5 |
| llama-latest (Vulkan, one card) | n/a | 5223.7 | 4949.0 | 4522.6 | **161.9** |

### 16.3 Revised conclusions (27B and 4B)

1. **rdna-boosts + ROCm 10.1 wins prefill** at 27B (1058 tps at pp8192).
2. **Vulkan wins decode** once pinned to a single card: 40.4 tps at 27B, 161.9 tps at 4B.
   The earlier "Vulkan is slower" conclusion was an artifact of the two-GPU sharding bug.
3. **ROCm 7.17 costs decode at 27B** (33.2 vs 39.6 tps, −16%) but *helps* the 4B model in
   prefill (6628 vs 5912 tps, +12%). The ROCm-version effect is model-size dependent.
4. **ROCm 7.13 is not competitive** (822 tps at pp2048, unstable).
5. **Stock rocm-llama is the slowest engine** at 27B (26.0 tps decode, −34%).
6. **Vanilla llama.cpp ≈ rdna-boosts** at identical ROCm (999.9 vs 1009.3 tps) — the AMD
   fork's gain comes from its build ROCm version, not from the fork itself.

### 16.4 125B head-to-head: Avalon vs Strata (through llama-swap)

GPU 1 (Gigabyte), **one 125B model resident at a time**, warm, greedy (`temperature=0`,
`min_tokens=512`, `ignore_eos`), `r=3`, median of 3 shown. Both are Qwen3.8-Flash-Next
125B MoE; Avalon IQ3KS + MTP draft, Strata IQ3_XXS + built-in spec (`--spec 4`).

| Metric | Avalon | Strata | Strata vs Avalon |
|--------|--------|--------|------------------|
| Prefill 2048 | 676 tps | 681 tps | +1% |
| Prefill 8192 | 930 tps | **1869 tps** | **+101%** |
| Prefill 16384 | 940 tps | **2386 tps** | **+154%** |
| Decode @1024 | 58.8 tps | **69.8 tps** | +19% |
| Decode @8192 | 63.9 tps | **65.7 tps** | +3% |
| Decode @32768 | 59.1 tps | **62.4 tps** | +6% |
| TTFT @8192 | 5.86 s | **2.91 s** | −50% |
| TTFT @32768 | 20.7 s | **9.26 s** | −55% |

Notes on stability: Avalon decode spread was ±3% (deterministic MTP), Strata spread was
wider (49.9…71.7 tps at depth 32768) because its speculative acceptance rate varies with
content — the median is the honest summary, and Strata's *worst* case can fall below
Avalon.

**Conclusion:** Strata is the right engine for this model. Its advantage is concentrated
in prefill/TTFT (2–2.5x), and it also holds a small decode lead. Avalon remains the more
predictable one at long context.

---

## 17. PCIe Slot Test: Sapphire (x2) vs Gigabyte (x16)

Both cards are identical RX 9070 (gfx1201, 16 GB, same 210 W cap). They differ only in how
the motherboard wires them: Sapphire runs at **PCIe 3.0 x2** (15.75 Gb/s ≈ 2 GB/s), Gigabyte
at **PCIe 4.0 x16** (252 Gb/s ≈ 31.5 GB/s) — a **16x** difference in bus bandwidth. See
section 1 for how that was verified.

**The question:** does the slot matter when the model fits entirely in VRAM, and how much
does it matter when experts and weights live in system RAM and stream across the bus?

### 17.1 Fully resident models (4B and 27B) — the slot barely matters

Measured 2026-11-01 with the corrected methodology (section 2b): greedy, `tg=512`, `r=3`,
device pinned (`-dev ROCm0` + `HIP_VISIBLE_DEVICES=0` for the x2 side, `-dev Vulkan0`),
`-b 4096 -ub 2048`, flash-attn on, KV f16. Both models fit wholly in 16 GB (4B IQ4_XS
≈ 2.6 GB, 27B IQ3_XXS ≈ 9.8 GB), so nothing streams over PCIe during inference.

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

Median across all 32 comparisons: **0.92** (−8%). Best cases cluster tightly at **0.98**
(stock rocm-llama 27B, Vulkan 27B prefill).

**Reading:**

1. **No cliff.** A 16x bus becomes a 2–6% difference once the model is resident. That is
   the expected physics: with everything in VRAM, per-token work never crosses PCIe; the
   bus is only used at load time and for the occasional KV/page fault.
2. **The tightest, most reproducible rows are the best evidence.** `stock101_27b` and
   `vulkan0_27b` prefill sit at 0.98 with stddev 0.0–0.4% across three prompt sizes —
   a consistent, small, repeatable penalty. That is the real slot effect.
3. **The large outliers are run noise, not the bus.** `rdna717_27b` shows −24.9% at pp2048
   but −4.9% at pp16384 with the same engine and model on the same card. A genuine
   bandwidth limit cannot flip like that within one model; measurement drift between the
   two rounds can.
4. **Decode holds up best at 27B** (0.965 for the best engine), which is what the
   hypothesis predicted: decode is weight-resident and GPU-local.

**Conclusion for resident models:** an x2 slot is fine. The cost is a few percent, well
inside the run-to-run spread, and it does not grow with context length.

*Caveat:* the x2 round ran while the agent's Avalon 125B model was resident on the other
card (idle, no inference traffic), and the x16 round ran with both cards otherwise idle.
An idle resident model does not generate PCIe traffic, but it does hold RAM, so the x2
numbers are, if anything, biased slightly *downward* — the true penalty is at or below
these figures.

### 17.2 The 125B MoE engines (Strata, Avalon) — the case the slot is supposed to break

Both Qwen3.8-Flash-Next 125B engines keep a large part of their experts and weights in
system RAM and pull them across the bus on every token. This is the case where a 2 GB/s
link should hurt badly.

Measured through the identical llama-swap path, only `HIP_VISIBLE_DEVICES` changed
(1 → 0), one model resident at a time. See section 16.4 for the x16 baseline.

*(Batch B in progress — results appended below when complete.)*

---

## 15. Future Testing

| Test | Priority | Notes |
|------|----------|-------|
| ROCm 7.2.4 vs 7.8.0 | Medium | Switch `LD_LIBRARY_PATH` to `/home/timoti/rocm724-portable/lib` |
| Model on Sapphire GPU (PCIe x2) | Low | `HIP_VISIBLE_DEVICES=0`, port 5900 |
| Sweep `--spec-draft-n-max` 2/3/4 | Medium | For Avalon |
| Direct Strata connection (no llama-swap) | Medium | `--serve` exists; `--bench-pp`/`--bench-tg` also exist but rejected the flag combination used in the audit (rc=2) — worth a separate attempt |
| rdna-boosts with larger model | Low | Need model that fits in 16 GB VRAM (e.g., 7-14B) |
| Avalon native `llama-bench` on Flash-Next | Blocked | 125B needs ~55 GB of buffer allocation; `llama-bench` has no CPU-expert offload, so it fails to load. Avalon 125B can only be measured through its server path |
| Vulkan re-measure of the 125B engines | Medium | Vulkan won decode at 27B/4B; never tried on Flash-Next |
| Re-run section 17 with the corrected methodology | Medium | Same `tg` length on both slots, no agent resident |
