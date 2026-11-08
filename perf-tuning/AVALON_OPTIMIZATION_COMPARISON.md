# Avalon Engine Optimization Comparison

**Date:** 2026-11-08  
**GPU:** AMD Radeon RX 9070 (RDNA4, gfx1201)  
**ROCm:** 10.1 (core-10.1)  
**Model:** Qwen3.8-Flash-Next 125B MoE (Avalon IQ3KS quant)  
**Test suite:** perf-bench (spec-decode, decode, prefill)

---

## Engine Versions

| | Old (Production) | New (Latest GitHub) |
|---|---|---|
| **Source** | `/media/timoti/Data/Avalon-new` | `/home/timoti/Avalon-new-build/Avalon-latest` |
| **Commit** | Unknown (pre-Nov 3) | `12abd35` (latest main) |
| **Build** | `0.8.0-dev` build 0, commit unknown | `0.8.0-dev` build 1, commit `12abd35` |
| **Compiler** | amdclang 24.0.0 (ROCm LLVM) | amdclang 24.0.0 (ROCm LLVM) |
| **HIP Compiler** | ROCm LLVM clang++ | ROCm LLVM clang++ |
| **Target** | gfx1201 | gfx1201 |
| **Key Flags** | GGML_HIP=ON, GGML_HIP_GRAPHS=ON, GGML_HIP_MMQ_MFMA=ON, GGML_HIP_NO_VMM=ON, GGML_NATIVE=ON, GGML_OPENMP=ON, AMDGPU_TARGETS=gfx1201, CMAKE_BUILD_TYPE=Release, BUILD_SHARED_LIBS=ON, LLAMA_OPENSSL=ON | **Identical** |

---

## Benchmark Results

### Speculative Decoding (spec-decode)
*Prompt: 8000 tokens, Generation: 1024 tokens, MTP speculative decoding*

| Metric | Old Engine | New Engine | Delta |
|--------|-----------|------------|-------|
| **Prefill (cold) t/s** | 1049.7 | 874.3 | **-16.7%** ⚠ |
| **Decode (warm) t/s** | 76.8 | 84.3 | **+9.7%** ✓ |
| **MTP Acceptance Rate** | 67.9% | 68.6% | **+1.0%** ✓ |
| Draft tokens per output | 0.986 | 0.979 | -0.7% |
| Accepted per output | 0.669 | 0.672 | +0.4% |

### Token Generation (decode - warm cache)
*Single streaming request per context depth, 128 output tokens*

| Context Depth | Old Engine (median t/s) | New Engine (median t/s) | Delta |
|--------------|------------------------|------------------------|-------|
| 1,024 | 63.1 | 68.7 | **+8.9%** |
| 8,192 | 70.8 | 69.8 | -1.4% |
| 32,768 | 72.2 | 72.6 | +0.6% |

### Prefill (cold cache, cache-busted)
*Unique prompts at several sizes, generation suppressed*

| Target Tokens | Actual Tokens | Old Engine (median t/s) | New Engine (median t/s) | Delta |
|--------------|---------------|------------------------|------------------------|-------|
| 512 | ~353 | 249.2 | 233.9 | **-6.1%** |
| 2,048 | ~1,352 | 734.4 | 738.1 | +0.5% |
| 8,192 | ~5,349 | 1,038.7 | 773.1 | **-25.6%** ⚠ |

### Prefill with `-ub 4092` (New Engine Only)
*Testing larger ubatch size for prefill improvement*

| Target Tokens | Actual Tokens | New Engine `-ub 2048` | New Engine `-ub 4092` | Delta |
|--------------|---------------|----------------------|----------------------|-------|
| 512 | ~352 | 233.9 | 211.9 | **-9.4%** |
| 2,048 | ~1,352 | 738.1 | 721.7 | -2.2% |
| 8,192 | ~5,350 | 773.1 | **990.9** | **+28.2%** ✓ |

**Finding:** `-ub 4092` significantly improves prefill at 8k context (+28.2%), closing most of the gap vs old engine (990.9 vs 1038.7 = -4.6%). Small contexts slightly regress.

---

## Summary

| Category | Winner | Notes |
|----------|--------|-------|
| **Spec-decode generation** | **New** | +9.7% faster token generation with MTP |
| **Spec-decode prefill** | Old | New is 16.7% slower on cold prefill |
| **Plain decode (warm)** | ~Tie | New slightly better at short context, equal at long |
| **Plain prefill (cold, -ub 2048)** | **Old** | Old significantly faster at 8k context (25.6% gap) |
| **Plain prefill (cold, -ub 4092)** | ~Tie | New catches up at 8k (+28%), small contexts slightly worse |
| **MTP acceptance** | ~Tie | Nearly identical (67.9% vs 68.6%) |

---

## Analysis

The new engine (commit `12abd35`) shows a **clear trade-off**:

- **Strengths:** Better speculative decoding throughput (+9.7%), slightly better MTP acceptance
- **Weaknesses:** Significantly slower prefill at default `-ub 2048`, especially at longer contexts (-25.6% at 8k tokens)

**Key finding:** Increasing `-ub` from 2048 to 4092 on the new engine **mostly closes the prefill gap** at 8k context (990.9 vs 1038.7 t/s, only -4.6%), at the cost of small regressions at 512/2k tokens.

---

## Recommendation

**Do NOT replace the production build yet** without further testing. However:

1. **Test `-ub 4092` in production** - it may close the prefill gap for the new engine
2. **Investigate the prefill regression** - compare CPU-side expert dispatch scheduling between commits
3. **Test with `--moe-cache-cpu-overlap` and `GGML_SCHED_PREFETCH_EXPERTS` tuning**
4. **Re-evaluate after upstream fixes** or when the prefill gap is closed

---

## rdna-boosts Update (v16-6050b467c-r235)

**Status:** Updated and rebuilt with identical options

| | Old (Production) | New (r235) |
|---|---|---|
| **Source** | `/home/timoti/Downloads/llama.cpp` | `/home/timoti/rdna-boosts-build/llama.cpp-r235` |
| **Base Commit** | 6050b467c | 6050b467c (same) |
| **Fork Tip** | 69d36099b | 69d36099b (same) |
| **Release** | r235 | r235 (same) |
| **Build** | `0.7.0-dev` build 11903, commit 69d36099b | `0.7.0-dev` build 11903, commit 69d36099b |
| **Host Compiler** | GCC 13.3.0 | GCC 13.3.0 |
| **HIP Compiler** | ROCm LLVM clang++ | ROCm LLVM clang++ |
| **Key Flags** | GGML_HIP=ON, GGML_HIP_GRAPHS=ON, GGML_HIP_MMQ_MFMA=ON, GGML_HIP_NO_VMM=ON, GGML_HIP_RCCL=ON, GGML_NATIVE=ON, GGML_OPENMP=ON, AMDGPU_TARGETS=gfx1201, CMAKE_BUILD_TYPE=Release, BUILD_SHARED_LIBS=ON, LLAMA_OPENSSL=ON, GGML_CCACHE=ON, GGML_VULKAN=OFF, GGML_CUDA=OFF | **Identical** |

**Author Notes (from release v16-6050b467c-r235):**
- PR #283 promoted: Fixed a host split input bug where inputs >1 MiB were incorrectly using async copy instead of synchronous fallback (affected token embeddings at large ubatch)
- Latent, not live: r234 vs r235 prefill logits byte-identical (0 of 1,013,178,324 B at -ub 512)
- Cost within arm spread (-0.17% / -0.30% / +0.08%)
- All gates passed: validate-set, per-block build 3/3, coherence 4 arms, prefill-logits 100%, host-pool 41/41, check-gpu-faults clean, test-backend-ops 251/251

**New in r235 (from worklog):**
- The prefill gap is NOT the transport engine or VRAM copies (measured on PCIe5 x16 host)
- One stream per consumer chain is optimal; extra streams add no bandwidth and delay pipeline
- Sync copy out of hipHostMalloc is 27% slower (gate calibration issue)
- Three VRAM copies are separate budget pools; shrinking ring VRAM doesn't convert to residency
- TODO #283 (GGML_CUDA_GRAPH_OPT branch streams collision), #284 (defer ring redirect restore), --load-mode none disables host-experts pool

---

## Raw Data References

| Run ID | Engine | Tests | Timestamp |
|--------|--------|-------|-----------|
| `20261108-154329` | Old (baseline) | spec-decode | 15:43:29 |
| `20261108-155053` | **New** | spec-decode | 15:50:53 |
| `20261108-155242` | **New** | decode | 15:52:42 |
| `20261108-155426` | **New** | prefill (-ub 2048) | 15:54:26 |
| `20261108-155619` | Old (re-verify) | spec-decode | 15:56:19 |
| `20261108-155803` | Old (re-verify) | decode | 15:58:03 |
| `20261108-155941` | Old (re-verify) | prefill | 15:59:41 |
| `20261108-160006` | Old (re-verify) | prefill | 16:00:06 |
| `20261108-161038` | **New** | prefill (-ub 4092) | 16:10:38 |

All results stored in: `/mnt/d/lmstudio/ai-driven-projects/perf-bench/results/runs.csv`

---

## Built Artifacts (Preserved)

| Engine | Binary Path | Status |
|--------|-------------|--------|
| Avalon Old (Production) | `/media/timoti/Data/Avalon-new/build/bin/llama-server` | **Active in llama-swap** |
| Avalon New (GitHub latest) | `/home/timoti/Avalon-new-build/Avalon-latest/build/bin/llama-server` | Ready for testing |
| rdna-boosts Old (Production) | `/home/timoti/Downloads/llama.cpp/build/bin/llama-server` | **Active in llama-swap** |
| rdna-boosts New (r235) | `/home/timoti/rdna-boosts-build/llama.cpp-r235/build/bin/llama-server` | Ready for testing |