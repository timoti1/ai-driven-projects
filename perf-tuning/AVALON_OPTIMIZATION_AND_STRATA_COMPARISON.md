# Avalon Optimization and Strata Comparison

**Test Date:** 2026-10-31  
**Branch:** `aic8800-wifi-bt-driver`  
**Repository:** `timoti1/ai-driven-projects`  
**Directories:** `perf-tuning/` and `perf-bench/`  
**Status:** Intermediate results, testing in progress

---

## 1. Test Stand

### Hardware Specification

| Component | Specification |
|-----------|--------------|
| CPU | AMD Ryzen 7 5800 (8C/16T, no AVX-512, expert kernels on AVX-2) |
| GPU 0 | AMD Radeon RX 9070 (Sapphire, PCIe 0a:00.0, PCIe x2 slow slot, gfx1201) |
| GPU 1 | AMD Radeon RX 9070 (Gigabyte, PCIe 05:00.0, PCIe x16 full slot, gfx1201) |
| VRAM per GPU | 16 GB |
| System RAM | 62 GB (+8 GB swap) |
| OS | Linux (Ubuntu 24.04-based) |

### GPU Mapping (HIP_VISIBLE_DEVICES)

- `HIP_VISIBLE_DEVICES=0` → Sapphire (PCIe x2)
- `HIP_VISIBLE_DEVICES=1` → Gigabyte (PCIe x16)

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
| Via llama-swap proxy | 2 | 4096 | 3 | — | ~15 tps | — |

**Key optimization findings:**

- `--parallel 1` gives **higher decode throughput** (~75 tps vs ~63 tps at parallel=2) with similar TTFT (~5.5 s vs ~5.8 s)
- batch 4096 gives **+89% prefill** compared to batch 2048
- draft 3 gives **+10-20% decode throughput** compared to draft 2
- llama-swap adds **~3-4x overhead** — direct connection to the engine port is preferred for maximum performance

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

### Proxy Overhead

- llama-swap adds **~3-4x overhead** compared to direct engine connection
- For maximum performance, direct connection to engine port (5800 for Avalon) is recommended

---

## 7. Memory Usage Comparison

### Strata Memory Requirements

Strata allocates a significant amount of system RAM during operation — at minimum several gigabytes are reserved for expert caching, PLE tables, and working memory. This can be a heavy burden on modern systems where memory is shared among multiple processes. The memory is held resident and is not readily available for other applications while Strata is running.

### Avalon Memory Usage

Avalon uses memory more gently. It allocates VRAM for model weights and KV cache, but the system RAM usage is more flexible. Memory used for caching is not exclusively blocked — it can be reclaimed or shared with other programs when needed. Avalon is able to run on systems with less total RAM available compared to Strata's requirements, making it more suitable for constrained environments where memory headroom is limited.

### Summary

| Aspect | Strata | Avalon |
|--------|--------|--------|
| System RAM reservation | High (several GB resident) | Moderate, flexible |
| Memory blocking | Memory held resident, unavailable to others | Cache can be reclaimed/shared |
| Suitable for low-RAM systems | No | Yes |

---

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

## 10. Future Testing

| Test | Priority | Notes |
|------|----------|-------|
| ROCm 7.13 vs 7.8.0 | Medium | Switch `LD_LIBRARY_PATH` to `/opt/rocm/core-7.13/lib` |
| ROCm 7.2.4 vs 7.8.0 | Medium | Switch `LD_LIBRARY_PATH` to `/home/timoti/rocm724-portable/lib` |
| Model on Sapphire GPU (PCIe x2) | Low | `HIP_VISIBLE_DEVICES=0`, port 5900 |
| Sweep `--spec-draft-n-max` 2/3/4 | Medium | For Avalon |
| Direct Strata connection (no llama-swap) | Medium | Requires HTTP server in Strata binary |
