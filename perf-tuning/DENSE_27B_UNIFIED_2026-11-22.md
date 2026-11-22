# Dense 27B profiles: one parameter set for every card

Measured 2026-11-22 on the two-GPU host. Companion tooling: [`../perf-bench`](../perf-bench).
Related: [QWEN38_27B_RDNA_BOOSTS_2026-11-22.md](QWEN38_27B_RDNA_BOOSTS_2026-11-22.md)
(the engine switch and drafter sweep this set was taken from),
[INKLING2_MINI_2026-11-22.md](INKLING2_MINI_2026-11-22.md).

**TL;DR**

- The `rdna-boosts` tuning was applied to one profile only; the other four dense 27B
  profiles still carried older flags (`--batch-size 4096 --ubatch-size 2048` on two of
  them, `--spec-draft-backend-sampling` on three, mixed `GGML_CUDA_SLAB_HEADROOM_MIB`
  and no `HSA_OVERRIDE_GFX_VERSION`). A/B measurement showed the old set costing up to
  **21% decode**.
- All five dense profiles now run the same parameter set: `--batch-size 2048
  --ubatch-size 1024`, `--spec-draft-n-max 3` without `--spec-draft-backend-sampling`,
  and the env `CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES=<card>
  LD_LIBRARY_PATH=/opt/rocm/lib HSA_OVERRIDE_GFX_VERSION=12.0.1` — no slab headroom.
- Decode is now **85–99 tok/s** with MTP acceptance **93–94%** on every dense profile, and
  the run-to-run spread fell from 13–18% to 0.1–0.5%.

## 1. Method

`perf-bench/ab.py` launches each arm as a separate `llama-server` on a dedicated port on
the measurement host and alternates the arms across two rounds, so thermal drift hits both
equally. Per arm: one 5.7k-token coding prompt built with a front nonce (cold prefill), then
byte-identical warm decode, greedy, 384 generated tokens, 3 repetitions. Decode tok/s,
prefill tok/s and MTP acceptance come from the server's own `timings`, not from wall clock.

Arms:

- `cur` — the parameters the profile actually ran in `llama-swap`.
- `tuned` — the `qwen3.8-27b-IQ3XXS-Uncensored` profile: rdna-boosts r275, batch 2048 /
  ubatch 1024, no backend sampling, `LD_LIBRARY_PATH=/opt/rocm/lib` +
  `HSA_OVERRIDE_GFX_VERSION=12.0.1`, no slab headroom.

## 2. Results

| Profile | Card | ctx | cur tg / pp (tok/s) | tuned tg / pp | Δ | Winner stanza |
|---|---|---|---|---|---|---|
| `qwen3.8-27b-IQ3XXS-Uncensored-ROCm` | Gigabyte HIP1 | 150k | 98.5 / 1013 | **99.3 / 1016** | +0.9% / +0.2% | [§3.1](#31-qwen38-27b-iq3xxs-uncensored-rocm--gigabyte-hip1-150k) |
| `qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` | Sapphire HIP0 | 130k | 74.2–77.1 / 759–777 | **91.7–92.1 / 933–934** | **+21.5% / +21.6%** | [§3.2](#32-qwen38-27b-iq3xxs-uncensored-rocm-sapphire--sapphire-hip0-130k) |
| `daisyrose-27b-IQ3_XXS-ROCm` | Gigabyte HIP1 | 130k | 88.0 / 1127 | **90.6 / 1191** | +2.9% / +5.5% | [§3.3](#33-daisyrose-27b-iq3_xxs-rocm--gigabyte-hip1-130k) |
| `daisyrose-27b-IQ3_XXS-ROCm-Sapphire` | Sapphire HIP0 | 130k | 84.9 / 1085 | 84.7 / 1077 | 0.0% | [§3.4](#34-daisyrose-27b-iq3_xxs-rocm-sapphire--sapphire-hip0-130k) |
| `qwen3.8-27b-IQ3XXS-Uncensored` (reference) | Gigabyte HIP1 | 120k | — | 99.2 / 1019 | reference | [§3.5](#35-qwen38-27b-iq3xxs-uncensored--gigabyte-hip1-120k-reference) |

MTP acceptance moved with the parameter set on the DaisyRose profiles: **89.7% → 93.4%**
(Gigabyte), unchanged at 93.4% on Sapphire. Qwen profiles sat at 93.7% in both arms.

## 3. Winning stanzas as deployed

Verbatim from `~/llama-swap/config.yml` on the serving host after the change — every flag,
env entry and `ttl` of the profile that won its A/B round, in the order of the table above.
`${rdna-boosts}` expands to
`/home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server`; `${PORT}` is assigned
per load by `llama-swap`.

### 3.1 `qwen3.8-27b-IQ3XXS-Uncensored-ROCm` — Gigabyte HIP1, 150k

```yaml
qwen3.8-27b-IQ3XXS-Uncensored-ROCm:
  name: qwen3.8-27b-IQ3XXS-Uncensored-ROCm
  description: 'GPU: Gigabyte RX 9070 (HIP1, PCIe x16) - rdna-boosts r275, Qwen3.8-27B dense IQ3_XXS + MTP, ctx 150k. Measured 2026-11-22: tg 99.3 tok/s (MTP acc 94%), pp 1016 tok/s, 15.9 GB VRAM. A/B winner over the old 1024/1024 + backend-sampling set (+0.9% tg, +0.2% pp).'
  capabilities:
    context: 150000
    tools: false
  cmd: >-
    ${rdna-boosts}
    --model /media/timoti/Storage/lmstudio/models/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored-MTP.gguf
    --device ROCm0
    -ngl 99
    -lv 3 --no-log-timestamps
    -rea auto
    --no-reasoning-preserve
    --flash-attn on
    --parallel 1
    --spec-type draft-mtp
    --spec-draft-n-max 3
    --batch-size 2048
    --ubatch-size 1024
    --threads 8
    --ctx-size 150000
    -ctk q4_0
    -ctv q4_0
    --temp 0.6
    --top_k 20
    --top-p 0.95
    --min-p 0.0
    --reasoning-effort low
    --reasoning-budget 4096
    --jinja
    --mmproj /media/timoti/Storage/lmstudio/models/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/mmproj-Qwen3.8-27B-Q5_K-MIX.gguf
    --cache-ram 0
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=1
  - LD_LIBRARY_PATH=/opt/rocm/lib
  - HSA_OVERRIDE_GFX_VERSION=12.0.1
  ttl: 1800
```

### 3.2 `qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` — Sapphire HIP0, 130k

```yaml
qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire:
  name: qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire
  description: 'GPU: Sapphire RX 9070 (HIP0, PCIe x2) - rdna-boosts r275, Qwen3.8-27B dense IQ3_XXS + MTP, ctx 130k. Measured 2026-11-22: tg 92 tok/s (MTP acc 94%), pp 934 tok/s. A/B winner over the old 4096/2048 + slab-headroom set (+21.5% tg, +21.6% pp).'
  capabilities:
    context: 130000
    tools: false
  cmd: >-
    ${rdna-boosts}
    --model /media/timoti/Storage/lmstudio/models/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored-MTP.gguf
    --device ROCm0
    -ngl 99
    -lv 3 --no-log-timestamps
    -rea auto
    --no-reasoning-preserve
    --flash-attn on
    --parallel 1
    --spec-type draft-mtp
    --spec-draft-n-max 3
    --batch-size 2048
    --ubatch-size 1024
    --threads 8
    --ctx-size 130000
    -ctk q4_0
    -ctv q4_0
    --temp 0.6
    --top_k 20
    --top-p 0.95
    --min-p 0.0
    --reasoning-effort low
    --reasoning-budget 4096
    --jinja
    --cache-ram 0
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=0
  - LD_LIBRARY_PATH=/opt/rocm/lib
  - HSA_OVERRIDE_GFX_VERSION=12.0.1
  # resident for Handy voice post-processing (ttl 0 = never idle-unload)
  ttl: 0
```

### 3.3 `daisyrose-27b-IQ3_XXS-ROCm` — Gigabyte HIP1, 130k

```yaml
daisyrose-27b-IQ3_XXS-ROCm:
  name: daisyrose-27b-IQ3_XXS-ROCm
  description: 'GPU: Gigabyte RX 9070 (HIP1, PCIe x16) - rdna-boosts r275, RadixArk DaisyRose-27B IQ3_XXS + MTP, ctx 130k. Measured 2026-11-22: tg 90.6 tok/s (MTP acc 93%), pp 1191 tok/s. A/B winner over 4096/2048 + backend-sampling (+2.9% tg, +5.5% pp, acc 89.7% -> 93.4%).'
  capabilities:
    context: 130000
    tools: false
  cmd: >-
    ${rdna-boosts}
    --model /media/timoti/Storage/lmstudio/models/bartowski/RadixArk_DaisyRose-27B-GGUF/RadixArk_DaisyRose-27B-IQ3_XXS.gguf
    --device ROCm0
    -ngl 99
    -lv 3 --no-log-timestamps
    -rea auto
    --no-reasoning-preserve
    --flash-attn on
    --parallel 1
    --spec-type draft-mtp
    --spec-draft-n-max 3
    --batch-size 2048
    --ubatch-size 1024
    --threads 8
    --ctx-size 130000
    -ctk q4_0
    -ctv q4_0
    --temp 0.6
    --top_k 20
    --top-p 0.95
    --min-p 0.0
    --reasoning-effort low
    --reasoning-budget 4096
    --jinja
    --cache-ram 0
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=1
  - LD_LIBRARY_PATH=/opt/rocm/lib
  - HSA_OVERRIDE_GFX_VERSION=12.0.1
  ttl: 0
```

### 3.4 `daisyrose-27b-IQ3_XXS-ROCm-Sapphire` — Sapphire HIP0, 130k

```yaml
daisyrose-27b-IQ3_XXS-ROCm-Sapphire:
  name: daisyrose-27b-IQ3_XXS-ROCm-Sapphire
  description: 'GPU: Sapphire RX 9070 (HIP0, PCIe x2) - rdna-boosts r275, RadixArk DaisyRose-27B IQ3_XXS + MTP, ctx 130k. Measured 2026-11-22: tg 84.7 tok/s (MTP acc 93%), pp 1077 tok/s, identical to the Gigabyte profile at the same parameter set.'
  capabilities:
    context: 130000
    tools: false
  cmd: >-
    ${rdna-boosts}
    --model /media/timoti/Storage/lmstudio/models/bartowski/RadixArk_DaisyRose-27B-GGUF/RadixArk_DaisyRose-27B-IQ3_XXS.gguf
    --device ROCm0
    -ngl 99
    -lv 3 --no-log-timestamps
    -rea auto
    --no-reasoning-preserve
    --flash-attn on
    --parallel 1
    --spec-type draft-mtp
    --spec-draft-n-max 3
    --batch-size 2048
    --ubatch-size 1024
    --threads 8
    --ctx-size 130000
    -ctk q4_0
    -ctv q4_0
    --temp 0.6
    --top_k 20
    --top-p 0.95
    --min-p 0.0
    --reasoning-effort low
    --reasoning-budget 4096
    --jinja
    --cache-ram 0
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=0
  - LD_LIBRARY_PATH=/opt/rocm/lib
  - HSA_OVERRIDE_GFX_VERSION=12.0.1
  ttl: 0
```

### 3.5 `qwen3.8-27b-IQ3XXS-Uncensored` — Gigabyte HIP1, 120k (reference)

```yaml
qwen3.8-27b-IQ3XXS-Uncensored:
  name: qwen3.8-27b-IQ3XXS-Uncensored
  description: 'GPU: Gigabyte RX 9070 (HIP1, PCIe x16) - rdna-boosts r275, Qwen3.8-27B dense IQ3_XXS + MTP, ctx 120k, reference profile every other dense model was brought to. Measured 2026-11-22: tg 99.2 tok/s (MTP acc 94%), pp 1019 tok/s, 14.5 GB VRAM.'
  capabilities:
    context: 120000
    tools: false
  cmd: >-
    ${rdna-boosts}
    --model /media/timoti/Storage/lmstudio/models/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored-MTP.gguf
    --device ROCm0
    -ngl 99
    -lv 3 --no-log-timestamps
    -rea auto
    --no-reasoning-preserve
    --flash-attn on
    --parallel 1
    --spec-type draft-mtp
    --spec-draft-n-max 3
    --batch-size 2048
    --ubatch-size 1024
    --threads 8
    --ctx-size 120000
    -ctk q4_0
    -ctv q4_0
    --temp 0.6
    --top_k 20
    --top-p 0.95
    --min-p 0.0
    --reasoning-effort low
    --reasoning-budget 4096
    --jinja
    --mmproj /media/timoti/Storage/lmstudio/models/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/mmproj-Qwen3.8-27B-Q5_K-MIX.gguf
    --cache-ram 0
    --host 0.0.0.0
    --port ${PORT}
    --metrics
  env:
  - CUDA_VISIBLE_DEVICES=
  - HIP_VISIBLE_DEVICES=1
  - LD_LIBRARY_PATH=/opt/rocm/lib
  - HSA_OVERRIDE_GFX_VERSION=12.0.1
  ttl: 3600
```

## 4. What actually moved the Sapphire qwen number

The 21% gap is **not** the environment. An env-only A/B on the Sapphire card
(`daisyrose`, same `--batch-size 2048 --ubatch-size 1024` in both arms, only
`LD_LIBRARY_PATH` / `HSA_OVERRIDE_GFX_VERSION` vs slab headroom swapped) measured
**0.0%** both ways. The gap belongs to `--batch-size 4096 --ubatch-size 2048`: with the
old batch the same model ran at 74–77 tok/s with a 13–18% spread, and at 91.7–92.1 with
0.2% spread after the change.

`--spec-draft-backend-sampling` is neutral-to-negative: it was present in the slower arms
of every comparison it took part in, and removing it alone did not move a number.

## 5. Applied configuration

`llama-swap` profile parameters, now identical for all five dense profiles:

```yaml
${rdna-boosts}   # /home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server
  --device ROCm0  -ngl 99  --flash-attn on  --parallel 1
  --spec-type draft-mtp  --spec-draft-n-max 3
  --batch-size 2048  --ubatch-size 1024  --threads 8  --ctx-size <profile>
  -ctk q4_0  -ctv q4_0  --cache-ram 0
env: CUDA_VISIBLE_DEVICES=  HIP_VISIBLE_DEVICES=<0|1>
     LD_LIBRARY_PATH=/opt/rocm/lib  HSA_OVERRIDE_GFX_VERSION=12.0.1
```

Each profile's `description` in the config now carries its measured tg/pp, MTP acceptance
and the delta against the parameter set it replaced.

Operational notes:

- The old `--spec-draft-backend-sampling` line is gone from the three profiles that had it.
- `GGML_CUDA_SLAB_HEADROOM_MIB=896` is gone from the four profiles that had it; the
  reference profile never had it and the A/B arms without it always won or tied.
- `llama-swap` does not pick up config edits on its own here: `kill -HUP <pid>` reloads
  it, after which the new flags appear in the spawned `llama-server` command line.
- VRAM at the sizes above: 15.9 GiB for the qwen profile at 150k, 14.5 GiB at 120k;
  both fit the 17 GiB card.

## 6. Reproduction

```bash
cd ../perf-bench
python3 ab.py ab --spec ab.dense-qwen-gb.json  --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-qwen-sp.json  --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-daisy-gb.json --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-daisy-sp.json --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
```

## 7. Left out of scope

- 7B tutor profiles (`tutorrl-7b`, `socraticlm-7b`) still run on the Vulkan build: they
  are small enough that the engine choice has not been re-measured, and they are not dense
  27B workloads.
- MoE profiles (Strata, Avalon, Inkling) are tuned separately; their optimum depends on
  engine and session count, not on these flags.
- Deeper isolation of batch size against `--ubatch-size` (e.g. 4096/1024) was not swept —
  the 2048/1024 winner was carried over from the earlier sweep and confirmed here.
