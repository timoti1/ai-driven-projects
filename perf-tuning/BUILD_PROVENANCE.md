# Build provenance: Avalon and rdna-boosts

Companion to [MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md). That document
reports what was measured; this one records **how the measured binaries were
built**, because on 3 November a compiler mismatch invalidated one comparison, and
the engine that was mis-built is the one carrying the interactive session.

Nothing here is host-specific: paths are placeholders, and the values that matter
(toolchain, target, flags) are reproducible on any RDNA4 box.

---

## Why this file exists

An A/B of two engine builds is only an A/B of *code* if the toolchain and flags are
identical. Yesterday's MoE-engine comparison failed that condition:

| | production binary | the "new" build it was compared against |
|---|---|---|
| source | commit `9617344db` | `origin/main` = `6cc179c6c`, 386 commits ahead |
| host compiler | **amdclang 24.0.0** (ROCm LLVM) | **GCC 13.3.0** |
| HIP compiler | ROCm LLVM `clang++` | ROCm LLVM `clang++` (same) |
| reported | `0.6.0-dev` build 1 | `0.8.0-dev` build 0, `commit unknown` |

Two variables moved at once — 386 commits *and* the host compiler — so the observed
gap could not be assigned to either. The build script that produced the new binary
never set `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER`, so CMake silently fell back to
`/usr/bin/cc`, which is GCC on this distribution.

A second provenance problem sat underneath the first: the new tree was reconfigured
and cleanly rebuilt at 22:02, after the 19:50 measurement. The artifact that was
measured no longer existed on disk. Its `--version` output said `build 0, commit
unknown`, so it cannot be recovered.

---

## The compiler is really two compilers

A HIP build has a host compiler and a device compiler, and CMake records them
separately:

```
CMAKE_C_COMPILER / CMAKE_CXX_COMPILER    <- host code: server, common, llama, ggml-base, ggml-cpu
CMAKE_HIP_COMPILER                       <- device kernels: ggml-hip, the ggml-cuda/*.cu template instances
```

On this machine every build — rdna-boosts, production Avalon, and the rebuild —
resolves `CMAKE_HIP_COMPILER` to the same ROCm LLVM `clang++`. **The GPU kernels are
therefore identical regardless of the host compiler.** What the host compiler choice
changes is the CPU-side path: request handling, sampling, batch scheduling,
`ggml-base` allocation, and the llama.cpp graph assembly.

That bounds the size of the confound rather than dismissing it. On a MoE engine
where decode is dominated by expert dispatch and host-side bookkeeping, host codegen
is not a negligible term — but it also means a measured gap of a few percent cannot
be blamed on kernel quality. The honest statement about yesterday's number is that
it is unattributed, not that it was small.

---

## Avalon: the project mandates amdclang

This is not a stylistic preference. The engine's own installer requires the ROCm
LLVM toolchain and configures with it:

```sh
# from the project's install.sh (paraphrased, paths as placeholders)
<rocm>/bin/amdclang++ must exist, or the installer aborts
cmake -S <engine-dir> -B <engine-dir>/build \
  -DGGML_HIP=ON -DAMDGPU_TARGETS=<gfx> \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=<rocm>/bin/amdclang \
  -DCMAKE_CXX_COMPILER=<rocm>/bin/amdclang++
cmake --build <engine-dir>/build -j<N> --target llama-server
```

Two caveats for anyone reproducing it on RDNA4:

- The installer's tested matrix is **ROCm 7.2.4 / RDNA3 (`gfx1100`)**. Our host runs
  **ROCm 10.1** with **`gfx1201`** (RDNA4), so `AMDGPU_TARGETS` must be passed
  explicitly; the installer's own `rocminfo` probe and generation check are written
  for RDNA3.
- The installer's ROCm version check reads `<rocm>/.info/version`, which is empty on
  this ROCm install, so it takes its "version unknown" branch and prints
  `ROCm version unknown (tested: 7.2.4)`. **That warning is an artifact of the empty
  version file, not a verdict on our stack.** It does not mean our ROCm is older than,
  or unsupported relative to, the tested 7.2.4.

### The ROCm stack actually in use

The host has two ROCm cores installed side by side, both shipped by the same
`amdgpu-install` release and both containing `gfx1201` binaries:

| core | hipBLASLt | `gfx1201` payload | used by |
|---|---|---|---|
| `core-10.1` | 1.4 | present | **everything**: Avalon (production and rebuild), rdna-boosts, and both running `llama-server` processes |
| `core-7.13` | 1.3 | present | nothing that computes — only `rocm-smi` resolves there |

`amdclang` itself resolves into `core-10.1/lib/llvm` (AMD clang 24.0.0, HIP runtime
7.16), and `ldd` on the built `libggml-hip.so` confirms `libamdhip64`, `libhipblas`,
`libhipblaslt` and `libLLVM` all come from `core-10.1`, as does the `gfx1201`
`Kernels.so` mapped into the live processes. So every number in
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md) was produced on `core-10.1`, and
no measurement has ever been taken against `core-7.13` — the choice of 10.1 is the
installed-and-linked default, not a benchmarked winner. If anyone wants the
hipBLASLt 1.3 vs 1.4 question settled, that is a separate experiment, not a
re-reading of existing data.

The production binary's `CMakeCache.txt` matches that recipe, and adds the defaults
the project turns on by itself. Flags that select kernels, from the production cache:

```
GGML_HIP=ON  GGML_HIP_GRAPHS=ON  GGML_HIP_MMQ_MFMA=ON  GGML_HIP_NO_VMM=ON
GGML_NATIVE=ON  GGML_OPENMP=ON  AMDGPU_TARGETS=gfx1201
CMAKE_BUILD_TYPE=Release  BUILD_SHARED_LIBS=ON
CMAKE_C_COMPILER=<rocm>/bin/amdclang      CMAKE_CXX_COMPILER=<rocm>/bin/amdclang++
CMAKE_HIP_COMPILER=<rocm-llvm>/bin/clang++
```

## The rebuild: same toolchain, same flags as production

```sh
# build_avalon_amdclang.sh  (kept on the bench host; engine dir is a git worktree)
SRC=<engine-checkout>; DST=<build-dir>; COMMIT=$(git -C "$SRC" rev-parse --short origin/main)
git -C "$SRC" worktree add --detach "$DST" "$COMMIT"

cmake -B "$DST/build" \
  -DCMAKE_C_COMPILER=<rocm>/bin/amdclang \
  -DCMAKE_CXX_COMPILER=<rocm>/bin/amdclang++ \
  -DGGML_HIP=ON -DGGML_HIP_GRAPHS=ON -DGGML_HIP_MMQ_MFMA=ON -DGGML_HIP_NO_VMM=ON \
  -DGGML_NATIVE=ON -DGGML_OPENMP=ON -DAMDGPU_TARGETS=gfx1201 \
  -DLLAMA_OPENSSL=ON \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build "$DST/build" -j 12 --target llama-server
```

Result: `0.8.0-dev`, `built with Clang 24.0.0`, commit `6cc179c6c`, `BUILD_EXIT=0`,
~10 minutes with `-j 12` on 16 cores. The `--parallel 1` / renamed-model config
change described in
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md#configuration-now-live) points at
this binary.

Differences from a bare `install.sh` build, and why: the explicit `GRAPHS` /
`MMQ_MFMA` / `NO_VMM` / `NATIVE` / `OPENMP` / `BUILD_SHARED_LIBS` values restate the
production cache instead of relying on defaults, so the two binaries differ only in
source revision. `LLAMA_OPENSSL=ON` matches production too. The earlier
`Avalon-new` build is left in place as the record of the mis-built artifact.

---

## rdna-boosts: GCC is the supported path there, and the r191 → r206 A/B was clean

The question worth asking — was that comparison also compiler-confounded — has a
verifiable answer, and it is **no**:

```
<fork>/build/CMakeCache.txt   mtime 01 Nov 00:06
<fork>/build/bin/llama-server mtime 03 Nov 17:41   (r206)
```

The cache was configured once and never touched across the update, so both revisions
built with the same toolchain and the same flags:

```
CMAKE_C_COMPILER=/usr/bin/cc        (GCC 13.3.0)
CMAKE_CXX_COMPILER=/usr/bin/c++     (GCC 13.3.0)
CMAKE_HIP_COMPILER=<rocm-llvm>/bin/clang++
GGML_HIP=ON  GGML_HIP_GRAPHS=ON  GGML_HIP_MMQ_MFMA=ON  GGML_HIP_NO_VMM=ON
GGML_NATIVE=ON  GGML_OPENMP=ON  GGML_VULKAN=OFF  AMDGPU_TARGETS=gfx1201
CMAKE_BUILD_TYPE=Release  BUILD_SHARED_LIBS=ON  GGML_CCACHE=ON (ccache not installed -> inert)
```

The git reflog pins the two revisions: `r191-deployed` = `561696677`, checked out
back at 16:39, and `rdna-boosts` = `efaa60db0` ("r206", `b11887-16-gefaa60db0`) at
17:14 — same build directory, same cache, one changed input: the source.

Unlike Avalon, this fork is a llama.cpp fork, and a GCC host compiler with the ROCm
LLVM HIP compiler is the ordinary upstream build path. There is no project mandate
being violated, and no cross-compiler term inside the r191 → r206 delta, the
headroom sweep, or the drafter sweep. Those results stand.

What does **not** stand is comparing absolute t/s *between* the two engines: Avalon's
host code is amdclang, rdna-boosts' is GCC, they are different codebases on different
cards. The +110 % MoE figure is a within-engine MTP on/off comparison, which is the
only kind that survives here.

---

## Rules adopted

1. **Pin the toolchain explicitly.** Every configure passes
   `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER`. Never let CMake fall back to
   `/usr/bin/cc` — the fallback is silent and the version string is the only place
   it shows up.
2. **Match the engine's own recipe before inventing one.** Avalon's installer states
   the required toolchain; deviating from it is a second experimental variable.
3. **One changed input per A/B.** If the compiler must change, that is a separate
   experiment, measured as such.
4. **Record provenance with every measurement.** `--version` output, commit, build
   flags, and binary mtime go into the result file. A binary that reports
   `build 0, commit unknown` cannot anchor a claim.
5. **Never measure an artifact that can be overwritten.** A clean rebuild of the tree
   under measurement destroys the evidence. Tag a copy, or measure from a path that
   the next build will not touch.
6. **Verify cache continuity when comparing revisions of one build tree.** If
   `CMakeCache.txt` mtime predates both binaries, the toolchain was constant; that
   check is what cleared the rdna-boosts comparison.

---

## Status

- `6cc179c6c` built with the production toolchain: **done**, not yet measured.
- Measuring it requires loading the 125B MoE model, and both cards are at
  ~16.98 / 17.10 GiB — a second instance does not fit. The measurement therefore
  happens on the far side of the llama-swap restart that also switches the session
  onto the new binary, so it is a post-restart task, not a background one.
- The `spec begin: ctx_dft pos_max=… < N-1 … Drafts may degrade` warning that was
  read as the new build's defect appears **in the production binary's log as well**
  (18 occurrences), so it is not a signature of the new revision. Its cause is
  unestablished; see the corrected open items in
  [MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md#open-items).
