# Performance Benchmark Results: Avalon vs Strata on AMD RX 9070 (RDNA 4 / gfx1201)

## Overview

This document records performance testing of Qwen3.8-Flash-Next 125B MoE inference on a dual-GPU system
(2× AMD Radeon RX 9070, RDNA 4 / gfx1201, 16 GB VRAM each) running llama-swap as a model router.

The primary goal was to find the best engine + driver + configuration combination for this model,
measuring both **single-thread (--parallel 1)** and **dual-thread (--parallel 2)** performance,
with prompt processing (prefill) and token generation (decode) metrics.

## Hardware

| Component | Specification |
|-----------|--------------|
| CPU | AMD Ryzen (Matisse/Starship) |
| GPU 0 | AMD Radeon RX 9070 (Sapphire, 0a:00.0, PCIe x2 slow slot) |
| GPU 1 | AMD Radeon RX 9070 (Gigabyte, 05:00.0, PCIe x16 full slot) |
| VRAM per GPU | 16 GB |
| System RAM | 62 GB |
| OS | Linux (Ubuntu 24.04-based) |

GPU mapping (HIP_VISIBLE_DEVICES):
- `HIP_VISIBLE_DEVICES=0` → Sapphire (PCIe x2)
- `HIP_VISIBLE_DEVICES=1` → Gigabyte (PCIe x16)

## Software Stack

### llama-swap
- Path: `/home/timoti/llama-swap/llama-swap`
- Config: `/home/timoti/llama-swap/config.yml`
- Listen: `0.0.0.0:8080`
- Version: v265 (commit d1e743f, build 2026-10-14)

### Engines tested

| Engine | Path | Fork/Bakend | llama.cpp version | Build date |
|--------|------|-------------|-------------------|------------|
| Avalon (HIP) | `/home/timoti/Avalon/build/bin/llama-server` | Avalon fork | 0.26.0 | 2026-10-31 |
| llama-latest (Vulkan) | `/home/timoti/Downloads/llama-latest/build/bin/llama-server` | llama.cpp upstream | 0.24.0 | 2026-10-15 |
| rocmfpx-runtime (Vulkan) | `/home/timoti/llama-rocmfpx-runtime/llama-server` | LaurentZuijdwijk b10641 (ROCmFP4 + adaptive speculation) | — | — |
| Strata engine | `/media/timoti/Data/repos/Strata/engine/strata` | Strata proprietary | — | — |

### Drivers / Runtimes

| Component | Version | Path |
|-----------|---------|------|
| ROCm (rocm-smi) | 4.0.0+3309c6114a, ROCm-SMI-LIB 7.8.0 | `/opt/rocm` |
| HIP / hipcc | 7.16.26385-0000000, AMD clang 24.0.0 | `/usr/bin/hipcc` |
| ROCm portable | 7.13 | `/opt/rocm/core-7.13/lib` |
| ROCm portable | 7.2.4 | `/home/timoti/rocm724-portable/lib` |
| Vulkan ICD (Mesa RADV) | 1.4.318, DRIVER_ID_MESA_RADV | `/home/timoti/mesa-build/libvulkan_radeon.so` |
| Vulkan API | 1.4.318 | system |

## Test Methodology

### Tool: perf-bench
- Path: `/home/timoti/ai-driven-projects/perf-bench/bench.py`
- Measures: health, prefill (prompt processing), decode (token generation), kv-cache
- Output: `results/runs.csv` + `results/run-<id>.json`

### Test parameters
- Prefill sizes: 512, 2048, 8192 tokens
- Decode context depths: 1024, 8192, 32768 tokens
- Decode tokens generated: 128 per request
- Repeat count: 2 per measurement

### Metrics recorded
- `prefill_tps` — tokens per second for prompt processing
- `decode_tps` — tokens per second for generation
- `first_token_s` — time to first token (TTFT)
- `completion` — number of tokens generated

## Models in config.yml

The following models are configured in `/home/timoti/llama-swap/config.yml`:

| Model ID | Engine | GPU | Quantization | Context |
|----------|--------|-----|--------------|---------|
| avalon-qwen3.8-flash-next-C2 | Avalon (HIP) | Gigabyte (HIP1) | IQ3_K (split 33 parts) | 200k |
| qwen3.8-27b-IQ3XXS | llama-latest (Vulkan) | Gigabyte (Vulkan1) | IQ3_XXS MTP | 209k |
| qwen3.8-27b-IQ3XXS-Uncensored | llama-latest (Vulkan) | Gigabyte (Vulkan1) | IQ3_XXS MTP | 261k |
| qwen3.8-27b-IQ3S-ROCm | rocm-llama (HIP) | Gigabyte (HIP1) | IQ3_S MTP | 105k |
| qwen3.8-flash-IQ3_S | Strata engine | Gigabyte (HIP1) | IQ3_S | 256k |
| qwen3.8-flash-IQ3_XXS | Strata engine | Gigabyte (HIP1) | IQ3_XXS | 256k |
| tiel-coder-35b-a3b | llama-latest (Vulkan) | Gigabyte (Vulkan1) | IQ4_XS MTP | 155k |
| qwen3.8-27b-IQ3XXS-Uncensored-Sapphire | llama-latest (Vulkan) | Sapphire (Vulkan0) | IQ3_XXS MTP | 170k |
| qwen3.8-27b-IQ3XXS-Sapphire | llama-latest (Vulkan) | Sapphire (Vulkan0) | IQ3_XXS MTP | 170k |
| qwen3.8-27b-IQ3S-ROCm-Sapphire | rocm-llama (HIP) | Sapphire (HIP0) | IQ3_S MTP | 105k |
| avalon-qwen3.8-flash-next-C2 (alt) | Avalon (HIP) | Gigabyte (HIP1) | IQ3_K | 200k |
| qwen3.8-27b-IQ3XXS-Uncensored-C2 | llama-latest (Vulkan) | Sapphire (Vulkan0) | IQ3_XXS v1.1 | 300k |
| qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire | rocm-llama (HIP) | Sapphire (HIP0) | IQ3_XXS MTP | 150k |

## Baseline: Avalon (HIP) on Gigabyte — Tested Configuration

**config.yml entry (modified):**
```yaml
avalon-qwen3.8-flash-next-C2:
  cmd: >-
    /home/timoti/Avalon/build/bin/llama-server
    -m <model-path>
    -c 200000
    -b 4096
    -ub 2048
    -fa on
    -ctk q8_0 -ctv q4_0
    --jinja
    --parallel 2
    -md <mtp-path>
    --spec-type draft-mtp
    --spec-draft-n-max 3
    -ubd 256
    -ctkd q8_0 -ctvd q4_0
    --temp 0.6 --top_k 30 --top-p 0.95
    --reasoning-effort low --reasoning-budget 4092
    --host 0.0.0.0 --port ${PORT} --metrics
  env:
    - CUDA_VISIBLE_DEVICES=
    - HIP_VISIBLE_DEVICES=1
  ttl: 86400
```

**Changes from original:**
- `-b 2048` → `-b 4096` (batch size)
- `-ub 1024` → `-ub 2048` (ubatch size)
- `--spec-draft-n-max 2` → `--spec-draft-n-max 3` (draft tokens)
- `HIP_VISIBLE_DEVICES=1` → model on Gigabyte (PCIe x16)

## Results Summary

### Avalon HIP, --parallel 1 (single-thread), batch 4096, draft 3 — BEST CONFIG

| Test | Depth | prefill_tps | decode_tps | first_token_s |
|------|-------|-------------|------------|---------------|
| prefill | 382 | 158.0 | — | — |
| prefill | 1381 | — | 689.2 | — |
| prefill | 5380 | — | 978.7 | — |
| prefill | 382 | 254.5 | — | — |
| prefill | 1381 | — | 580.3 | — |
| prefill | 5380 | — | 989.5 | — |
| decode | 1024 | — | 51.1 | 2.49 s |
| decode | 8192 | — | 69.2 | 5.48 s |
| decode | 32768 | — | 68.9 | 19.47 s |
| decode | 1024 | — | 67.2 | 2.52 s |
| decode | 8192 | — | 81.0 | 5.49 s |
| decode | 32768 | — | 78.0 | 19.50 s |

### Avalon HIP, --parallel 2 (dual-thread), batch 4096, draft 3

| Test | Depth | prefill_tps | decode_tps | first_token_s |
|------|-------|-------------|------------|---------------|
| prefill | 382 | ~236–258 | — | — |
| prefill | 1381 | — | ~681–706 | — |
| prefill | 5381 | — | ~936–947 | — |
| decode | 1024 | — | ~54–67 | ~2.5–2.8 s |
| decode | 8192 | — | ~58–68 | ~5.8 s |
| decode | 32768 | — | ~54–61 | ~21 s |

### Avalon HIP, --parallel 2 (dual-thread), batch 2048, draft 2 — ORIGINAL CONFIG

| Test | Depth | prefill_tps | decode_tps | first_token_s |
|------|-------|-------------|------------|---------------|
| prefill | 512 | ~140–244 | — | — |
| prefill | 2048 | ~401–437 | — | — |
| prefill | 8192 | ~495–499 | — | — |
| decode | 1024 | — | ~16–47 | ~2.6–2.7 s |
| decode | 8192 | — | ~44–49 | ~10.8 s |
| decode | 32768 | — | ~47–50 | ~37–40 s |

### llama-swap proxy overhead (port 8080 vs direct port 5800/5900)

| Measurement | Via swap (8080) | Direct (5800/5900) | Ratio |
|-------------|-----------------|--------------------|-------|
| decode 1024 | ~15 tps | ~47–64 tps | ~3–4x slower via swap |
| decode 8192 | ~15–17 tps | ~46–73 tps | ~3–4x slower via swap |

**Conclusion:** llama-swap adds significant proxy overhead. For maximum performance, connect directly to the engine port.

## What Still Needs Testing

### ✅ Completed

- **Avalon HIP with --parallel 1** (single-thread, live-tested 2026-10-31): ~75 tps decode @ 8K (range 69-81), ~984 tps prefill @ 8K (range 979-990), TTFT ~5.5 s
- **Avalon HIP with --parallel 2** (dual-thread): ~63 tps decode @ 8K, ~941 tps prefill @ 8K, TTFT ~5.8 s
- **Avalon HIP with --spec-draft-n-max 3** (draft 3): best config, better than draft 2

### ❌ Blocked — cannot test with current setup

| Engine | Blocker |
|--------|---------|
| **llama-latest (Vulkan 0.4.1-dev)** | Avalon GGUF uses custom MoE tensor names (`blk.0.ffn_down_exps.weight`) incompatible with standard llama.cpp. No Qwen3.8-27B GGUF files available. Cannot test with target Qwen3.8-Flash-Next 125B MoE model. |
| **rocmfpx-runtime (Vulkan)** | Same model incompatibility — based on llama.cpp, cannot load Avalon GGUF. |
| **Strata engine** | `per_layer_token_embd.weight` missing from Strata model shards — engine cannot launch with `--native`. Binary lacks `--serve` HTTP mode. Needs `libhipblas.so.3.4` (ROCm 7.13). Direct side-by-side test impossible — no shared model format. |

### ⬜ Not yet tested

| Test | Priority |
|------|----------|
| Direct side-by-side test (Avalon vs Strata) | High — **IMPOSSIBLE**: no shared model format, Avalon uses 33-shard GGUF, Strata uses native IQ packs |
| Different ROCm versions (7.13, 7.2.4 vs 7.8.0) | Medium |
| Model on Sapphire GPU (PCIe x2, slower bus) | Low |
| --spec-draft-n-max 2 vs 3 vs 4 sweep | Medium |

## GitHub Repository

Source: `https://github.com/timoti1/ai-driven-projects/tree/aic8800-wifi-bt-driver`
Relevant directories:
- `perf-bench/` — performance harness
- `perf-tuning/` — STRATA_OPTIMIZATION.md
- `quality-bench/` — quality benchmarks
- `llama-swap/` — model router
- `pi/` — pi agent
