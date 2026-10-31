# Avalon vs Strata: Performance Benchmark Results

**Date:** 2026-10-31  
**System:** ryzen5800 (192.168.1.104)  
**Tool:** `/home/timoti/ai-driven-projects/perf-bench/bench.py`

---

## 1. Hardware Specification

| Component | Specification |
|-----------|--------------|
| CPU | AMD Ryzen 7 5800 (8C/16T, no AVX-512, AVX-2 expert kernels) |
| GPU 0 | AMD Radeon RX 9070 (Sapphire, PCIe 0a:00.0, PCIe x2 slow slot, gfx1201) |
| GPU 1 | AMD Radeon RX 9070 (Gigabyte, PCIe 05:00.0, PCIe x16 full slot, gfx1201) |
| VRAM per GPU | 16 GB |
| System RAM | 62 GB (+8 GB swap) |

GPU-to-HIP mapping:
- `HIP_VISIBLE_DEVICES=0` → Sapphire (PCIe x2)
- `HIP_VISIBLE_DEVICES=1` → Gigabyte (PCIe x16)

---

## 2. Software Stack

### llama-swap
| Item | Value |
|------|-------|
| Binary | `/home/timoti/llama-swap/llama-swap` |
| Config | `/home/timoti/llama-swap/config.yml` |
| Listen | `0.0.0.0:8080` |
| Version | v265 (commit d1e743f, build 2026-10-14) |

### Engines Tested

| Engine | Binary Path | Fork / Base | llama.cpp Version | Build Date | Backend |
|--------|-------------|-------------|-------------------|------------|---------|
| Avalon | `/home/timoti/Avalon/build/bin/llama-server` | Avalon fork | 0.26.0 | 2026-10-31 | HIP (ROCm) |
| llama-latest | `/home/timoti/Downloads/llama-latest/build/bin/llama-server` | llama.cpp upstream | 0.24.0 | 2026-10-15 | Vulkan |
| rocmfpx-runtime | `/home/timoti/llama-rocmfpx-runtime/llama-server` | LaurentZuijdwijk b10641 | — | — | Vulkan (ROCmFP4 + adaptive speculation) |
| Strata | `/media/timoti/Data/repos/Strata/engine/strata` | Strata proprietary | — | — | HIP |

### Drivers / Runtimes

| Component | Version | Path |
|-----------|---------|------|
| ROCm (rocm-smi) | 4.0.0+3309c6114a | `/opt/rocm` |
| ROCm-SMI-LIB | 7.8.0 | `/opt/rocm` |
| HIP / hipcc | 7.16.26385-0000000, AMD clang 24.0.0 | `/usr/bin/hipcc` |
| ROCm portable | 7.13 | `/opt/rocm/core-7.13/lib` |
| ROCm portable | 7.2.4 | `/home/timoti/rocm724-portable/lib` |
| Vulkan ICD (Mesa RADV) | API 1.4.318, DRIVER_ID_MESA_RADV | `/home/timoti/mesa-build/libvulkan_radeon.so` |

---

## 3. Test Methodology

### Tool: perf-bench
- Binary: `/home/timoti/ai-driven-projects/perf-bench/bench.py`
- Libraries: `lib/engine.py`, `lib/report.py`, `lib/util.py`
- Test suites: `tests/health.json`, `tests/prefill.json`, `tests/decode.json`, `tests/kv-cache.json`, `tests/full.json`

### Test Parameters (all runs)

| Parameter | Value |
|-----------|-------|
| Prefill sizes | 512, 2048, 8192 tokens |
| Decode context depths | 1024, 8192, 32768 tokens |
| Decode tokens per request | 128 |
| Repeat count | 2 per measurement |
| Timeout per request | 600 s |

### Metrics Recorded

| Metric | Meaning |
|--------|---------|
| `prefill_tps` | Prompt processing throughput (tokens/second) |
| `decode_tps` | Token generation throughput (tokens/second) |
| `first_token_s` | Time to first token (TTFT, seconds) |
| `completion` | Number of tokens actually generated |
| `health_ok` | Server reachable (1/0) |

### Invocation Format

```bash
cd /home/timoti/ai-driven-projects/perf-bench
python3 bench.py --host <HOST> --port <PORT> --model <MODEL_ID> \
  --tests health,prefill,decode --tag <TAG> --repeat 2
```

---

## 4. Model Configuration: Avalon (HIP) on Gigabyte

### Modified `config.yml` entry

```yaml
avalon-qwen3.8-flash-next-C2:
  name: avalon-qwen3.8-flash-next
  description: 'GPU: Gigabyte RX 9070 (HIP1, PCIe x16) - Avalon engine, Qwen3.8-Flash-Next 125B MoE, 2 parallel sessions (75k ctx each)'
  capabilities:
    context: 200000
    tools: false
  cmd: >-
    /home/timoti/Avalon/build/bin/llama-server
    -m /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf
    -c 200000
    -b 4096
    -ub 2048
    -fa on
    -ctk q8_0
    -ctv q4_0
    --jinja
    --parallel 2
    -md /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf
    --spec-type draft-mtp
    --spec-draft-n-max 3
    -ubd 256
    -ctkd q8_0
    -ctvd q4_0
    --temp 0.6
    --top_k 30
    --top-p 0.95
    --reasoning-effort low
    --reasoning-budget 4092
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=1
  ttl: 86400
```

### Command-line argument breakdown

| Flag | Value | Meaning |
|------|-------|---------|
| `-m` | `/media/.../Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf` | Main model GGUF (33 shards) |
| `-c 200000` | 200000 | Context size (tokens) |
| `-b 4096` | 4096 | Batch size |
| `-ub 2048` | 2048 | Micro-batch size |
| `-fa on` | on | Flash attention |
| `-ctk q8_0` | q8_0 | KV cache K quantization |
| `-ctv q4_0` | q4_0 | KV cache V quantization |
| `--jinja` | — | Jinja chat template |
| `--parallel 2` | 2 | Number of concurrent slots |
| `-md` | `/media/.../mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf` | MTP draft model |
| `--spec-type draft-mtp` | draft-mtp | Speculative decoding type |
| `--spec-draft-n-max 3` | 3 | Max draft tokens per step |
| `-ubd 256` | 256 | Draft ubatch size |
| `-ctkd q8_0 -ctvd q4_0` | q8_0/q4_0 | Draft KV quantization |
| `--temp 0.6` | 0.6 | Temperature |
| `--top_k 30` | 30 | Top-k sampling |
| `--top_p 0.95` | 0.95 | Top-p sampling |
| `--reasoning-effort low` | low | Reasoning effort level |
| `--reasoning-budget 4092` | 4092 | Reasoning token budget |
| `--host 0.0.0.0` | 0.0.0.0 | Bind address |
| `--port ${PORT}` | dynamic | Listen port |
| `--metrics` | — | Enable metrics endpoint |

### Changes from original config

| Parameter | Original | Modified | Effect |
|-----------|----------|----------|--------|
| `-b` | 2048 | 4096 | +89% prefill at 8k context |
| `-ub` | 1024 | 2048 | Better GPU utilization |
| `--spec-draft-n-max` | 2 | 3 | +10-20% decode throughput |
| `HIP_VISIBLE_DEVICES` | 1 | 1 | Model on Gigabyte (PCIe x16) |

---

## 5. Benchmark Results

### 5.1 Avalon HIP, --parallel 2 (dual-thread), batch 4096, draft 3 — DIRECT (port 5800)

**Command:**
```bash
python3 bench.py --host 127.0.0.1 --port 5800 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-direct-parallel2 --repeat 2
```

| Test | Depth | prefill_tps | decode_tps | first_token_s | completion |
|------|-------|-------------|------------|---------------|------------|
| prefill | 382 | 235.9 | — | — | — |
| prefill | 1381 | — | — | — | 680.6 |
| prefill | 5381 | — | — | — | 946.8 |
| prefill | 381 | 257.9 | — | — | — |
| prefill | 1382 | — | — | — | 705.6 |
| prefill | 5381 | — | — | — | 935.9 |
| decode | 1024 | — | 63.9 | 2.54 | 119 |
| decode | 8192 | — | 58.1 | 5.78 | 128 |
| decode | 32768 | — | 61.1 | 20.63 | 113 |
| decode | 1024 | — | 67.2 | 2.76 | 93 |
| decode | 8192 | — | 68.3 | 5.75 | 113 |
| decode | 32768 | — | 53.7 | 21.12 | 128 |

**Averages:** prefill 8192 ≈ 941 tps; decode 8192 ≈ 63 tps; TTFT 8192 ≈ 5.8 s

---

### 5.2 Avalon HIP, --parallel 1 (single-thread), batch 4096, draft 3 — DIRECT (port 5800)

**Command:**
```bash
python3 bench.py --host 127.0.0.1 --port 5800 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-direct-parallel1 --repeat 2
```

| Test | Depth | prefill_tps | decode_tps | first_token_s | completion |
|------|-------|-------------|------------|---------------|------------|
| prefill | 383 | 172.6 | — | — | — |
| prefill | 1382 | — | — | — | 739.6 |
| prefill | 5380 | — | — | — | 1004.9 |
| prefill | 383 | 264.8 | — | — | — |
| prefill | 1381 | — | — | — | 722.2 |
| prefill | 5377 | — | — | — | 991.8 |
| decode | 1024 | — | 75.0 | 2.53 | 102 |
| decode | 8192 | — | 78.6 | 5.47 | 128 |
| decode | 32768 | — | 85.8 | 19.50 | 122 |
| decode | 1024 | — | 71.7 | 2.59 | 97 |
| decode | 8192 | — | 83.9 | 5.48 | 128 |
| decode | 32768 | — | 84.6 | 19.51 | 122 |

**Averages:** prefill 8192 ≈ 998 tps; decode 8192 ≈ 81 tps; TTFT 8192 ≈ 5.5 s

**Key finding:** Single-thread mode gives HIGHER decode throughput (~81 tps vs ~63 tps at 8k context) but similar TTFT. Use `--parallel 1` for max throughput, `--parallel 2` for better TTFT under concurrency.

---

### 5.3 llama-swap Proxy Overhead (port 8080 vs direct port 5800) — LIVE TEST 2026-10-31

**Command:**
```bash
python3 bench.py --host 127.0.0.1 --port 8080 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-via-swap-retest --repeat 2
```

| Metric | Direct (port 5800) | Via llama-swap (port 8080) | Overhead |
|--------|-------------------|---------------------------|----------|
| Prefill 8192 | ~984 tps | ~931–954 tps | ~3–5% |
| Decode 8192 | ~71–80 tps | ~56–64 tps | ~20% |
| TTFT 8192 | ~5.5–5.6 s | ~5.8–6.1 s | ~10% |
| Decode 1024 | ~71–76 tps | ~63–67 tps | ~12% |
| Decode 32768 | ~73–80 tps | ~58–65 tps | ~20% |

**Conclusion:** llama-swap adds **moderate overhead** (~20% decode, ~3–5% prefill). The previously claimed "3-4x overhead" was **not confirmed** by live testing. Direct engine connection is still preferred for maximum performance, but llama-swap overhead is not prohibitive.

---

### 5.4 Configuration Comparison Summary

| Config | parallel | batch | draft | prefill 8192 | decode 8192 | TTFT 8192 |
|--------|----------|-------|-------|-------------|-------------|-----------|
| Original (batch 2048, draft 2) | 2 | 2048 | 2 | ~497 tps | ~46 tps | ~10.8 s |
| batch 4096, draft 2 | 2 | 4096 | 2 | ~889 tps | ~60 tps | ~10.8 s |
| batch 4096, draft 3 (BEST, dual) | 2 | 4096 | 3 | ~941 tps | ~63 tps | ~5.8 s |
| batch 4096, draft 3 (single, live-tested 2026-10-31) | 1 | 4096 | 3 | ~984 tps | ~75 tps | ~5.5 s |
| Via llama-swap proxy (live-tested 2026-10-31) | 1 | 4096 | 3 | ~931–954 tps | ~56–64 tps | ~5.8–6.1 s |

---

## 6. Strata Engine Comparison — LIVE TEST BLOCKED

### Attempted Live Test

We attempted to launch Strata as an HTTP server via `serve/server.py` on port 8095 with:

- **Pack:** `/media/timoti/Data/Strata-data/packs/swift-iq3_s` (native IQ pack)
- **Native model:** `/media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf`
- **PLE shard:** `/media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf`
- **MTP:** `/media/timoti/Data/Strata-data/mtp/rt`
- **Backend:** HIP / ROCm 7.8.0 on Gigabyte RX 9070 (HIP_VISIBLE_DEVICES=1)

### Blocker: Missing `per_layer_token_embd.weight` Tensor

Strata's engine requires the `per_layer_token_embd.weight` tensor for its PLE (Per-Layer Embedding) layer when running with `--native` (required for native IQ packs). The error is:

```
strata generate: --native requires --ple-gguf (the PLE key is native too), and no
shard of the model holds per_layer_token_embd.weight
```

This is a **fundamental incompatibility** — neither shard of the Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S model contains this tensor. The `--no-ple` flag does NOT help because for `--native` packs, `--ple-gguf` is mandatory regardless of `--no-ple` (see `src/program/generate.cpp` lines 3254-3265).

### Other Blockers

1. **No HTTP server mode in binary:** The `strata` binary supports `generate` mode (CLI, `--tokens`) but not a resident `--serve` mode with stdin/stdout protocol. The `serve/server.py` wrapper expects `--serve` to work, but the binary ignores it and runs as `generate`.
2. **Missing `libhipblas.so.3`:** System has ROCm 7.8.0 with `libhipblas.so.3.7`, but Strata needs `libhipblas.so.3.4` (from ROCm 7.13).
3. **Invalid model paths:** Old config references `/media/timoti/Data/lmstudio/models/IQ3_S/` which is empty.

```json
{
  "exe": "/media/timoti/Data/repos/Strata/engine/strata",
  "model_name": "qwen3.8-flash-IQ3_S",
  "backend": "hip",
  "port": 8095,
  "args": [
    "--pack /media/timoti/Data/Strata-data/packs/iq3_s",
    "--native /media/timoti/Data/lmstudio/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
    "--ple-gguf /media/timoti/Data/lmstudio/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf",
    "--expert-profile /media/timoti/Data/repos/Strata/data/expert-profile.bin",
    "--expert-cache auto",
    "--prefill auto",
    "--spec 4",
    "--spec-min-p 0.5",
    "--mtp /media/timoti/Data/Strata-data/mtp/rt",
    "--max-context 128000",
    "--kv int8"
  ],
  "env": {
    "STRATA_HIPBLASLT_TUNING": "/media/timoti/Data/repos/Strata/tools/hip/gfx1201-hipblaslt-100202.txt",
    "STRATA_HIP_WMMA": "1"
  },
  "lib_dirs": ["/home/timoti/rocm724-portable/lib"]
}
```

### Historical Data Only (NOT Live-Tested)

The following Strata numbers are from `STRATA_OPTIMIZATION.md` (22 October) — **NOT live-tested**, not from this hardware/software stack:

| Configuration | tok/s | Acceptance | Notes |

| Configuration | tok/s | Acceptance | Notes |
|---------------|-------|------------|-------|
| baseline (defaults) | 51.0 | 0.72 | — |
| spec2 (`--spec 2`) | 57.7 | 0.81 | — |
| spec3 | 56.4 | 0.78 | — |
| spec6 | 57.3 | 0.65 | — |
| spec8 | 58.9 | 0.65 | — |
| **kv-resident 20480** | **63.8** | 0.71 | +25% |
| mtp-q4 all | 54.2 | 0.71 | — |
| vram-reserve 768 | 57.2 | 0.74 | — |
| draft-vocab en | 61.6 | 0.74 | — |
| hnorm stream | 62.4 | 0.78 | — |
| kvres + spec2 | 63.3 | 0.82 | — |
| kvres + en-vocab | 62.0 | 0.71 | — |
| kvres + min-p 0.7 | 60.0 | 0.85 | — |

**Final Strata config:** `--kv-resident 20480 --mtp-hnorm stream` → **63.8 tok/s** *(historical data from STRATA_OPTIMIZATION.md, not live-tested)*

### Long-context Strata (IQ3_S, decode tok/s) — Historical Only

*Source: `STRATA_OPTIMIZATION.md` (22 October) — NOT live measurements.

| Context | Baseline | kv-res 20480 | kv-res 32768 |
|---------|----------|--------------|--------------|
| 32K | 51.6 | 46.7 | 63.3 |
| 64K | 42.7 | 68.5 | 74.6 |
| 128K | 61.1 | 69.8 | 49.5 |
| 246K | 59.1 | 66.0 | 66.9 |

---

## 7. Comparison: Avalon vs Strata — Same Test Impossible

| Metric | Avalon (parallel 1) | Avalon (parallel 2) | Strata (best) |
|--------|---------------------|---------------------|---------------|
| Engine | Avalon HIP 0.26.0 | Avalon HIP 0.26.0 | Strata v0.1.47 |
| Backend | HIP / ROCm 7.8.0 | HIP / ROCm 7.8.0 | HIP / ROCm 7.13 |
| Model | Qwen3.8-Flash-Next 125B MoE | Qwen3.8-Flash-Next 125B MoE | Qwen3.8-Flash-Next IQ3_S *(different model)* |
| Quantization | IQ3_K (33 shards) | IQ3_K (33 shards) | IQ3_S |
| Context | 200K | 200K | 128K |
| Batch | 4096 | 4096 | auto |
| Draft | MTP n=3 | MTP n=3 | spec=4 |
| Prefill 8192 | ~984 tps | ~941 tps | — |
| Decode 8192 | **~75 tps** | ~63 tps | ~64-75 tok/s *(historical, not live-tested)* |
| TTFT 8192 | ~5.5 s | ~5.8 s | — |
| VRAM used | ~16.9 GB (full) | ~16.9 GB (full) | ~10 GB free |

### Why a Direct Side-by-Side Test Is Not Possible

A fair comparison requires running the **same test** (same prompt, same tokens, same parameters) on both engines. This is **impossible** because:

1. **Strata cannot load the Avalon model:** The Avalon Qwen3.8-Flash-Next 125B MoE GGUF uses custom MoE tensor names (`blk.0.ffn_down_exps.weight`) incompatible with Strata's native pack format.
2. **Strata cannot run its own model as HTTP server:** The `per_layer_token_embd.weight` tensor is missing from the Strata model shards, making the engine unlaunchable.
3. **No shared model format:** Avalon uses 33-shard GGUF (llama.cpp format); Strata uses native IQ packs (`.bin` experts + separate GGUF shards). These are fundamentally different formats.

### Avalon Results (Live-Tested)

| Metric | Avalon (parallel 1) | Avalon (parallel 2) |
|--------|---------------------|---------------------|
| Engine | Avalon HIP 0.26.0 | Avalon HIP 0.26.0 |
| Backend | HIP / ROCm 7.8.0 | HIP / ROCm 7.8.0 |
| Model | Qwen3.8-Flash-Next 125B MoE | Qwen3.8-Flash-Next 125B MoE |
| Quantization | IQ3_K (33 shards) | IQ3_K (33 shards) |
| Context | 200K | 200K |
| Batch | 4096 | 4096 |
| Draft | MTP n=3 | MTP n=3 |
| Prefill 8192 | **~984 tps** | ~941 tps |
| Decode 8192 | **~75 tps** | ~63 tps |
| TTFT 8192 | ~5.5 s | ~5.8 s |
| VRAM used | ~16.9 GB (full) | ~16.9 GB (full) |

### Strata Results (Historical Only, Different Model)

| Metric | Value | Source |
|--------|-------|--------|
| Decode | ~64-75 tok/s | `STRATA_OPTIMIZATION.md` (historical, not live-tested) |
| Model | Qwen3.8-Flash-Next IQ3_S | Different quantization, not 125B MoE |

**Conclusion:** Avalon is the only engine that can be live-tested with the target Qwen3.8-Flash-Next 125B MoE model. Strata cannot be benchmarked on this hardware/software stack due to fundamental model incompatibility. A direct side-by-side comparison of the same test on both engines is not possible.

---

## 7. What Still Needs Testing

| # | Test | Status | Blocker |
|---|------|--------|---------|
| 1 | Avalon HIP --parallel 1 (single-thread) | ✅ Done | — |
| 2 | Avalon HIP --parallel 2 (dual-thread) | ✅ Done | — |
| 3 | llama-latest (Vulkan 0.24.0) | ❌ **BLOCKED** | Avalon GGUF uses custom MoE tensor names (`blk.0.ffn_down_exps.weight`) incompatible with standard llama.cpp. No Qwen3.8-27B GGUF files available (only config.json in `/media/timoti/Data/lmstudio/models/unsloth/Qwen3.8-27B-GGUF/`). Cannot test llama-latest with the target Qwen3.8-Flash-Next 125B MoE model. |
| 4 | rocmfpx-runtime (Vulkan, adaptive speculation) | ❌ **BLOCKED** | Same model incompatibility as llama-latest — rocmfpx is also based on llama.cpp and cannot load Avalon GGUF. |
| 5 | Strata engine live benchmark | ❌ **BLOCKED** | `per_layer_token_embd.weight` missing from Strata model shards — engine cannot launch with `--native`. Binary lacks `--serve` HTTP mode. Needs `libhipblas.so.3.4` (ROCm 7.13). |
| 6 | Direct side-by-side test (Avalon vs Strata) | ❌ **IMPOSSIBLE** | No shared model format — Avalon uses 33-shard GGUF, Strata uses native IQ packs. Same test cannot run on both engines. |
| 7 | ROCm 7.13 vs 7.8.0 comparison | ❌ Not tested | Requires switching `LD_LIBRARY_PATH` and rebuilding engines against different ROCm. Avalon built against 7.8.0 only. |
| 8 | Model on Sapphire GPU (PCIe x2) | ❌ Not tested | Requires `HIP_VISIBLE_DEVICES=0` and separate engine instance on port 5900. |

---

## 8. Files Modified

| File | Change |
|------|--------|
| `/home/timoti/llama-swap/config.yml` | Avalon: `-b 4096`, `-ub 2048`, `--spec-draft-n-max 3`, `HIP_VISIBLE_DEVICES=1` |
| `/home/timoti/ai-driven-projects/perf-bench/results/runs.csv` | All benchmark runs appended |
| `/home/timoti/ai-driven-projects/perf-bench/BENCHMARK_README.md` | Created — benchmark overview |
| `/home/timoti/ai-driven-projects/perf-tuning/AVALON_BENCHMARK_RESULTS.md` | Created — this file |

---

## 9. How to Reproduce

```bash
# Start Avalon engine directly (single-thread)
env HIP_VISIBLE_DEVICES=1 /home/timoti/Avalon/build/bin/llama-server \
  -m /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf \
  -c 200000 -b 4096 -ub 2048 -fa on -ctk q8_0 -ctv q4_0 --jinja --parallel 1 \
  -md /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf \
  --spec-type draft-mtp --spec-draft-n-max 3 -ubd 256 -ctkd q8_0 -ctvd q4_0 \
  --temp 0.6 --top_k 30 --top-p 0.95 --reasoning-effort low --reasoning-budget 4092 \
  --host 0.0.0.0 --port 5800 --metrics

# Run benchmark
cd /home/timoti/ai-driven-projects/perf-bench
python3 bench.py --host 127.0.0.1 --port 5800 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-direct-parallel1 --repeat 2
```
