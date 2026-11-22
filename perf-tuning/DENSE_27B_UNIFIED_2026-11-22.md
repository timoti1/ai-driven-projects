# Dense 27B on RDNA4: engine choice, one parameter set, deployed stanzas

Measured 2026-11-22 on the two-GPU host (Gigabyte RX 9070 in the x16 slot, Sapphire RX 9070
in the chipset x2 slot). Companion tooling: [`../perf-bench`](../perf-bench). Related:
[INKLING2_MINI_2026-11-22.md](INKLING2_MINI_2026-11-22.md) (MoE profile on the same host),
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md) (first drafter sweep),
[VULKAN_SAPPHIRE_2026-11-04.md](VULKAN_SAPPHIRE_2026-11-04.md) (why Vulkan lags on the
chipset slot).

## 1. Results at a glance

- **39.9 → 78.4 tok/s** for the dense 27B by running it on the `rdna-boosts` HIP build
  instead of the Vulkan build with the MTP drafter on. Prefill went 388 → 709 tok/s.
- The drafter is almost free on the HIP build (**+66%**: 40.8 → 67.9 tok/s) and nearly
  worthless on Vulkan (**+6%**: 37.8 → 39.9). The engine choice is what unlocks it.
- Best drafter setting: `--spec-type draft-mtp --spec-draft-n-max 3` with `-ub 1024`.
  Longer draft blocks lose (n-max 4: 62.2, n-max 6: 53.3 tok/s).
- That tuning had reached **one** profile only; the other four dense profiles still carried
  older flags (`--batch-size 4096 --ubatch-size 2048` on two, `--spec-draft-backend-sampling`
  on three, mixed `GGML_CUDA_SLAB_HEADROOM_MIB`, no `HSA_OVERRIDE_GFX_VERSION`). Interleaved
  A/B put the old set up to **21% behind** on decode.
- All five dense profiles now run one identical parameter set. Decode is **85–99 tok/s**
  with MTP acceptance **93–94%**, and run-to-run spread fell from 13–18% to 0.1–0.5%.
- Decode numbers below were measured with the model resident on the card, greedy, on a
  ~5.7k-token prompt; they are not comparable to wall-clock figures from an agent session.

## 2. Method

### 2.1 Engine and drafter comparison

Same model, same card, same prompt class (code review task, greedy, ctx 120000), one engine
build at a time; tok/s taken from the server's own `timings` (`prompt_per_second`,
`predicted_per_second`) rather than from wall clock, and draft acceptance from
`draft_n` / `draft_n_accepted`. Each build was loaded on a dedicated port so no other
workload shared the card.

### 2.2 Interleaved A/B of profile parameters

`perf-bench/ab.py` launches each arm as a separate `llama-server` on a dedicated port on the
measurement host and alternates the arms across two rounds, so thermal drift hits both
equally. Per arm: one 5.7k-token coding prompt built with a front nonce (cold prefill), then
byte-identical warm decode, greedy, 384 generated tokens, 3 repetitions. Decode tok/s,
prefill tok/s and MTP acceptance again come from the server's own `timings`.

Arms:

- `cur` — the parameters the profile actually ran in `llama-swap`.
- `tuned` — the `qwen3.8-27b-IQ3XXS-Uncensored` profile: `rdna-boosts` r275, batch 2048 /
  ubatch 1024, no backend sampling, `LD_LIBRARY_PATH=/opt/rocm/lib` +
  `HSA_OVERRIDE_GFX_VERSION=12.0.1`, no slab headroom.

## 3. Engine matrix (code prompt, ctx 120000, greedy)

| Engine | Device | Drafter | tg tok/s | pp tok/s | Acceptance |
|---|---|---|---|---|---|
| Vulkan (`llama-latest/build`, custom Mesa ICD) | Vulkan1 | MTP n3 | 39.9 | 388 | 50% |
| Vulkan | Vulkan1 | none | 37.8 | 465 | — |
| mainline HIP (`llama-latest/build-hip`) | ROCm0 | MTP n3 | 43.6 | 543 | 49% |
| `llama-rdna3` fork (Inkling fusions) | ROCm0 | MTP n3 | 43.7 | 558 | 49% |
| `rdna-boosts` r275 (HIP, stew675) | ROCm0 | MTP n3 | 67.9 | 709 | 48% |
| `rdna-boosts` r275 | ROCm0 | none | 40.8 | 772 | — |

Two independent effects. The drafter's verify batch is cheap on `rdna-boosts` and expensive
on Vulkan; and prefill is 1.5–1.8× faster on HIP, which matters more than decode for agent
workloads that re-read a long conversation. Without any drafter `rdna-boosts` still wins on
prefill (772 vs 465), so the engine choice stands on its own.

The Inkling fusion fork matches mainline on a dense model (43.7 vs 43.6): its fusions are
model-specific, and its mmvq retune targets gfx1100, not RDNA4.

## 4. Drafter flag sweep (`rdna-boosts`, MTP, ctx 120000)

| Variant | tg tok/s | Acceptance | VRAM |
|---|---|---|---|
| n-max 2 | 67.6 | 59% | 14.4 GiB |
| n-max 3 | 67.9 | 48% | 14.5 GiB |
| n-max 4 | 62.2 | 39% | 14.7 GiB |
| n-max 6 | 53.3 | 29% | 14.9 GiB |
| `-ub 512` | 66.3 | 47% | 14.2 GiB |

KV quantisation changed nothing in speed here either (q4_0 vs q8_0); q4_0 is kept so 120k
context fits in 14.5 GiB.

## 5. Parameter A/B across the five dense profiles

| Profile | Card | ctx | cur tg / pp (tok/s) | tuned tg / pp | Δ | Winner stanza |
|---|---|---|---|---|---|---|
| `qwen3.8-27b-IQ3XXS-Uncensored-ROCm` | Gigabyte HIP1 | 150k | 98.5 / 1013 | 99.3 / 1016 | +0.9% / +0.2% | [§6.1](#61-qwen38-27b-iq3xxs-uncensored-rocm--gigabyte-hip1-150k) |
| `qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` | Sapphire HIP0 | 130k | 74.2–77.1 / 759–777 | 91.7–92.1 / 933–934 | +21.5% / +21.6% | [§6.2](#62-qwen38-27b-iq3xxs-uncensored-rocm-sapphire--sapphire-hip0-130k) |
| `daisyrose-27b-IQ3_XXS-ROCm` | Gigabyte HIP1 | 130k | 88.0 / 1127 | 90.6 / 1191 | +2.9% / +5.5% | [§6.3](#63-daisyrose-27b-iq3_xxs-rocm--gigabyte-hip1-130k) |
| `daisyrose-27b-IQ3_XXS-ROCm-Sapphire` | Sapphire HIP0 | 130k | 84.9 / 1085 | 84.7 / 1077 | 0.0% | [§6.4](#64-daisyrose-27b-iq3_xxs-rocm-sapphire--sapphire-hip0-130k) |
| `qwen3.8-27b-IQ3XXS-Uncensored` (reference) | Gigabyte HIP1 | 120k | — | 99.2 / 1019 | reference | [§6.5](#65-qwen38-27b-iq3xxs-uncensored--gigabyte-hip1-120k-reference) |

MTP acceptance moved with the parameter set on the DaisyRose profiles: 89.7% → 93.4%
(Gigabyte), unchanged at 93.4% on Sapphire. Qwen profiles sat at 93.7% in both arms.

## 6. Winning stanzas as deployed

Verbatim from `~/llama-swap/config.yml` on the serving host after the change: every flag,
env entry and `ttl` of the profile that won its A/B round, in the order of the table above.
`${rdna-boosts}` expands to
`/home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server`; `${PORT}` is assigned
per load by `llama-swap`.

### 6.1 `qwen3.8-27b-IQ3XXS-Uncensored-ROCm` — Gigabyte HIP1, 150k

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

### 6.2 `qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire` — Sapphire HIP0, 130k

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

### 6.3 `daisyrose-27b-IQ3_XXS-ROCm` — Gigabyte HIP1, 130k

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

### 6.4 `daisyrose-27b-IQ3_XXS-ROCm-Sapphire` — Sapphire HIP0, 130k

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

### 6.5 `qwen3.8-27b-IQ3XXS-Uncensored` — Gigabyte HIP1, 120k (reference)

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

## 7. What actually moved the Sapphire qwen number

The 21% gap is not the environment. An env-only A/B on the Sapphire card (`daisyrose`, same
`--batch-size 2048 --ubatch-size 1024` in both arms, only `LD_LIBRARY_PATH` /
`HSA_OVERRIDE_GFX_VERSION` vs slab headroom swapped) measured 0.0% both ways. The gap belongs
to `--batch-size 4096 --ubatch-size 2048`: with the old batch the same model ran at
74–77 tok/s with a 13–18% spread, and at 91.7–92.1 with a 0.2% spread after the change.

`--spec-draft-backend-sampling` is neutral-to-negative: it was present in the slower arm of
every comparison it took part in, and removing it alone did not move a number.

## 8. Applied configuration and operational notes

Parameter set now identical for all five dense profiles:

```yaml
${rdna-boosts}   # /home/timoti/rdna-boosts-build/llama.cpp-r275/build/bin/llama-server
  --device ROCm0  -ngl 99  --flash-attn on  --parallel 1
  --spec-type draft-mtp  --spec-draft-n-max 3
  --batch-size 2048  --ubatch-size 1024  --threads 8  --ctx-size <profile>
  -ctk q4_0  -ctv q4_0  --cache-ram 0
env: CUDA_VISIBLE_DEVICES=  HIP_VISIBLE_DEVICES=<0|1>
     LD_LIBRARY_PATH=/opt/rocm/lib  HSA_OVERRIDE_GFX_VERSION=12.0.1
```

Each profile's `description` in the config carries its measured tg/pp, MTP acceptance and
the delta against the parameter set it replaced. Operational notes:

- The old `--spec-draft-backend-sampling` line is gone from the three profiles that had it.
- `GGML_CUDA_SLAB_HEADROOM_MIB=896` is gone from the four profiles that had it; the
  reference profile never had it, and the A/B arms without it always won or tied.
- Switching a profile from the Vulkan build to HIP means removing `--device Vulkan1`,
  `VK_DRIVER_FILES=/home/timoti/mesa-build/radeon_icd.json` and
  `RADV_PERFTEST=coop_matrix`. Leaving them in place makes the server exit with
  `no ROCm-capable device is detected`.
- `llama-swap` does not pick up config edits on its own here: `kill -HUP <pid>` reloads it,
  after which the new flags appear in the spawned `llama-server` command line.
- VRAM: 15.9 GiB for the qwen profile at 150k, 14.5 GiB at 120k — both fit the 17 GiB card.
- After the switch the API reported `--spec-type draft-mtp` active with acceptance 62% on a
  120k session and 78.4 tok/s; the interleaved A/B later reproduced this as 99 tok/s on a
  shorter, non-agent prompt.

## 9. Reproduction

```bash
cd ../perf-bench
python3 ab.py ab --spec ab.dense-qwen-gb.json  --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-qwen-sp.json  --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-daisy-gb.json --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
python3 ab.py ab --spec ab.dense-daisy-sp.json --reps 3 --rounds 2 --gen 384 --prompt-tokens 5000
```

## 10. Left out of scope

- 7B tutor profiles (`tutorrl-7b`, `socraticlm-7b`) still run on the Vulkan build: the
  engine choice has not been re-measured for them, and they are not dense 27B workloads.
- MoE profiles (Strata, Avalon, Inkling) are tuned separately; their optimum depends on the
  engine and the session count, not on these flags.
- Deeper isolation of batch size against `--ubatch-size` (e.g. 4096/1024) was not swept; the
  2048/1024 winner came from the earlier sweep and was confirmed here.
