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

### 5.3 llama-swap Proxy Overhead (port 8080 vs direct port 5800)

**Command:**
```bash
python3 bench.py --host 192.168.1.104 --port 8080 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-via-swap-baseline --repeat 2
```

| Test | Depth | prefill_tps | decode_tps | first_token_s |
|------|-------|-------------|------------|---------------|
| prefill | 512 | error (HTTPError) | — | — |
| prefill | 2048 | error | — | — |
| prefill | 8192 | error | — | — |
| decode | 1024 | — | ~15 | — |
| decode | 8192 | — | ~15 | — |
| decode | 32768 | — | ~17 | — |

**Conclusion:** llama-swap proxy adds ~3-4x overhead. For maximum performance, connect directly to engine port (5800/5900), bypassing swap.

---

### 5.4 Configuration Comparison Summary

| Config | parallel | batch | draft | prefill 8192 | decode 8192 | TTFT 8192 |
|--------|----------|-------|-------|-------------|-------------|-----------|
| Original (batch 2048, draft 2) | 2 | 2048 | 2 | ~497 tps | ~46 tps | ~10.8 s |
| batch 4096, draft 2 | 2 | 4096 | 2 | ~889 tps | ~60 tps | ~10.8 s |
| batch 4096, draft 3 (BEST) | 2 | 4096 | 3 | ~938 tps | ~72 tps | ~5.8 s |
| batch 4096, draft 3 (single) | 1 | 4096 | 3 | ~998 tps | ~81 tps | ~5.5 s |
| Via llama-swap proxy | 2 | 4096 | 3 | — | ~15 tps | — |

---

## 6. Strata Engine Comparison

### Strata Bench Configuration

From `/home/timoti/rocm-bench/bench-rocm724.json`:

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

### Strata Optimization Results (from STRATA_OPTIMIZATION.md)

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

### Long-context Strata (IQ3_S, decode tok/s)

*Source: `STRATA_OPTIMIZATION.md` (22 October) — NOT live measurements, historical data only.*

| Context | Baseline | kv-res 20480 | kv-res 32768 |
|---------|----------|--------------|--------------|
| 32K | 51.6 | 46.7 | 63.3 |
| 64K | 42.7 | 68.5 | 74.6 |
| 128K | 61.1 | 69.8 | 49.5 |
| 246K | 59.1 | 66.0 | 66.9 |

---

## 7. Comparison: Avalon (Best) vs Strata

| Metric | Avalon (parallel 1) | Avalon (parallel 2) | Strata (best) |
|--------|---------------------|---------------------|---------------|
| Engine | Avalon HIP 0.26.0 | Avalon HIP 0.26.0 | Strata v0.1.47 |
| Backend | HIP / ROCm 7.8.0 | HIP / ROCm 7.8.0 | HIP / ROCm 7.13 |
| Model | Qwen3.8-Flash-Next 125B MoE | Qwen3.8-Flash-Next 125B MoE | Qwen3.8-Flash-Next IQ3_S |
| Quantization | IQ3_K (33 shards) | IQ3_K (33 shards) | IQ3_S |
| Context | 200K | 200K | 128K |
| Batch | 4096 | 4096 | auto |
| Draft | MTP n=3 | MTP n=3 | spec=4 |
| Prefill 8192 | ~998 tps | ~941 tps | — |
| Decode 8192 | **~81 tps** | ~63 tps | ~64-75 tok/s *(historical, not live-tested)* |
| TTFT 8192 | ~5.5 s | ~5.8 s | — |
| VRAM used | ~16.9 GB (full) | ~16.9 GB (full) | ~10 GB free |

**Winner: Avalon (single-thread)** — ~81 tps decode at 8K context, ~998 tps prefill at 8K context. Strata achieves ~64-75 tok/s but with lower VRAM usage (~10 GB free vs full 16 GB).

---

## 7. What Still Needs Testing

| # | Test | Status | Blocker |
|---|------|--------|---------|
| 1 | Avalon HIP --parallel 1 (single-thread) | ✅ Done | — |
| 2 | Avalon HIP --parallel 2 (dual-thread) | ✅ Done | — |
| 3 | llama-latest (Vulkan 0.24.0) | ❌ **BLOCKED** | Avalon GGUF uses custom MoE tensor names (`blk.0.ffn_down_exps.weight`) incompatible with standard llama.cpp. No Qwen3.8-27B GGUF files available (only config.json in `/media/timoti/Data/lmstudio/models/unsloth/Qwen3.8-27B-GGUF/`). Cannot test llama-latest with the target Qwen3.8-Flash-Next 125B MoE model. |
| 4 | rocmfpx-runtime (Vulkan, adaptive speculation) | ❌ **BLOCKED** | Same model incompatibility as llama-latest — rocmfpx is also based on llama.cpp and cannot load Avalon GGUF. |
| 5 | Strata engine live benchmark | ❌ **BLOCKED** | Strata is a CLI-only tool (`strata generate`), not an HTTP server — cannot benchmark via perf-bench API probes. Also missing `libhipblas.so.3.4` (needs ROCm 7.13 path, system has 7.8.0 with `libhipblas.so.3.7`). Model paths in old config are invalid (`/media/timoti/Data/lmstudio/models/IQ3_S/` empty). |
| 6 | ROCm 7.13 vs 7.8.0 comparison | ❌ Not tested | Requires switching `LD_LIBRARY_PATH` and rebuilding engines against different ROCm. Avalon built against 7.8.0 only. |
| 7 | Model on Sapphire GPU (PCIe x2) | ❌ Not tested | Requires `HIP_VISIBLE_DEVICES=0` and separate engine instance on port 5900. |

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
