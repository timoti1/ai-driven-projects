# maya-ik2 on gfx1201 (RX 9070, 16 GB): HIP port notes

Built from this checkout on the desktop `ryzen5800` (2 × RX 9070, ROCm/HIP 7.16, clang 24).
Upstream ships `maya-ik2` for CUDA only; the HIP path was the "P0-3 spike" in CMake
(`STRATA_HIP_IK2_SPIKE`), which compiled but did not link. This tree makes it run.

## What was changed

`src/ik2/ik2_kernels.cu`, all guarded by `__HIP_PLATFORM_AMD__`:

| CUDA primitive | HIP replacement |
|---|---|
| `mma.sync.aligned.m16n8k16` | quad shuffles + `__hmul2`, FP32 sums (same C/A/B fragment layout, no tensor cores) |
| `ldmatrix.sync.aligned.m8n8.x4` (and `.trans`) | shared-memory reads at the addresses gathered with `__shfl_sync` |
| `cp.async.cg/ca` + `commit`/`wait_group` | plain 16/4-byte copies to shared memory, commit and wait are no-ops |
| `mul.rn.f16x2` / `sub.rn.f16x2` | `__hmul2` / `__hsub2` |
| `__cvta_generic_to_shared`, `asm` float constraints | generic-address casts, `v` integer constraints |

The fused prefill attention kernel needs 88 KB of shared memory, above gfx12's 64 KB, so
it is not used: run with `IK2_FLASH=0` (attention through the logits path).

`CMakeLists.txt`: `tests/ik2_expert_bench.cu` does not exist in this branch; the target is
now added only when the file is present, so `-DSTRATA_HIP_IK2_SPIKE=ON` configures.

## Build

```bash
cmake -S . -B build-hip -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_HIP_IK2_SPIKE=ON \
  -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_PREFILL_MMQ=ON -DSTRATA_BUILD_TESTS=OFF \
  -DCMAKE_HIP_ARCHITECTURES=gfx1201 -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ \
  -DCMAKE_HIP_COMPILER_ROCM_ROOT=/opt/rocm -DCMAKE_PREFIX_PATH=/opt/rocm
cmake --build build-hip -j 10 --target maya-ik2
```

Kernels checked by `build-hip/ik2_kernels_test` against the FP64 reference: decode and
multi-query attention (FP32/FP16/FP8 KV), routing, NVFP4 and Q8_0 experts all pass. The
`attn_flash` case cannot launch (shared memory, see above).

## Weights and configs

* `models/` → `unsloth/Inkling-2-Mini-GGUF` `UD-Q4_K_XL` (17.6 GB), `mmproj-BF16`, and
  `thinkingmachines/Inkling-2-Mini` `mtp.safetensors` (symlinks into the model store).
* `ik2/tokenizer` — `tools/strata_tokenizer.py`.
* `ik2-solo.json` — one Gigabyte RX 9070, 131,072 context, FP8 KV, drafter, 10.5 GiB
  expert cache. Registered in llama-swap as `inkling-2-mini-maya-hip`.
* `ik2-dual.json` — both cards, 131,072 context, all experts cached (slower, see below).

## Measured on this machine (Gigabyte RX 9070, PCIe x16)

| Setup | Prefill | Decode |
|---|---:|---:|
| maya-ik2 HIP, 1 card, 128k ctx, drafter | 727–835 tok/s | 45.7–48.8 tok/s |
| maya-ik2 HIP, 1 card, 16k ctx | 710–952 tok/s | 47–49.5 tok/s |
| maya-ik2 HIP, 2 cards, 128k ctx, all experts cached | 632–980 tok/s | 29.8–33.1 tok/s |
| llama.cpp fork (`fusion-llama`), UD-IQ3_XXS, 2 × 100k | 1014 tok/s | 53.3–54.8 tok/s |
| Strata engine, Qwen3.8-Flash-Next IQ3_S (reference) | 1191–1234 tok/s | 67.8–70.9 tok/s |

Upstream gets 125 tok/s from the same file on a 24 GB RTX 3090, where all 14.7 GiB of
experts stay in VRAM. A 16 GB card holds about 10.5 GiB of them next to the dense weights
and the KV cache, so roughly a fifth of the expert reads of every token come from host
memory or the CPU lane. That gap, not the kernel arithmetic, is what limits this box.

The tensor-core kernels are the missing piece for prefill: this build emulates
`mma.sync` with shuffles, which costs the prompt throughput (835 vs the 2,700 tok/s
upstream reports on a 3090) and the deep-context decode.

Two cards are slower even with every expert cached: the layer split sends each token's
hidden state across the x2 PCIe link twice, and that costs more than the misses it removes.
