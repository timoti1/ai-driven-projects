# Vulkan on the chipset-attached GPU — why it lags, and whether the model fits in VRAM

Investigated 2026-11-04 on the two-GPU host, for the models that run on the GPU
reachable only through the chipset (`Vulkan0` in the serving config). Companion
tooling: [`../perf-bench`](../perf-bench). Related:
[BUILD_PROVENANCE.md](BUILD_PROVENANCE.md),
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md).

**TL;DR**

- **The "KV spills to system RAM" theory is not the main cause** for the flagship
  170k / single-slot configuration: it fits in VRAM with 0.6–2.4 GiB to spare
  (budget below). The 300k / parallel-2 configuration of the *same weights* does
  **not** fit — it is over budget by roughly 0.7–1.7 GiB, and that is the entry
  where the spill intuition is correct.
- **The dominant gap is structural, not placement-related.** The Vulkan backend's
  gated-delta-net kernel is a *serial per-token recurrence in all-f32*. The HIP
  path has *chunked* GDN kernels on the RDNA4 matrix units. For a hybrid model
  where 48 of 64 layers are GDN, that is the prefill bottleneck.
- **Flash attention silently self-disables** in one observed Vulkan run: the
  auto-FA probe found the fused op landing on CPU and turned FA off. This happened
  with `auto`, and it is invisible unless you read the log.
- **The PCIe path really is slow** — x2 Gen3 (~1.6–2.0 GB/s effective), not the
  x16 Gen4 the GPU negotiates locally. So *if* something spills, or if an op runs
  on CPU per token, the penalty on this card is far larger than on the
  CPU-attached card. The config comment "slow PCIe x2 slot" is accurate.
- **Cooperative matrix is available** on both cards under the self-built Mesa
  snapshot (`VK_KHR_cooperative_matrix` rev 2, `cooperativeMatrix = true`). Coopmat
  is not the missing ingredient.

---

## 1. What was observed (evidence, not inference)

| # | Observation | Source |
|---|---|---|
| 1 | `resolve_fused_ops: layer 3 is assigned to device Vulkan0 but Flash Attention over K/V rows is assigned to device CPU (usually due to missing support)` followed by `Flash Attention over K/V rows not supported, set to disabled` | Vulkan smoke-run log, verbosity 3 |
| 2 | `model has unused tensor blk.64.*` (the MTP block) in a run started **without** `--spec-type draft-mtp` — i.e. that log's numbers carry no MTP benefit | same log |
| 3 | Vulkan GDN shader loops `for (uint t = 0; t < n_tokens; t++)` — a sequential recurrence; support gate requires **all inputs and output F32**, and `S_v ∈ {16,32,64,128}` | `gated_delta_net.comp`, Vulkan `supports_op` |
| 4 | HIP path ships **chunked** GDN prefill kernels, including a bf16 WMMA variant for this GPU family | `gated_delta_net_chunked*.cu` in the fork |
| 5 | Recurrent state is allocated on `model.dev_layer(i)` and logged as `RS buffer size = … MiB` — so GDN state lives on the GPU, not in host RAM | `llama-memory-recurrent.cpp` |
| 6 | `VK_KHR_cooperative_matrix` rev 2 present, `cooperativeMatrix = true` on both GPUs | `vulkaninfo` against the self-built ICD |
| 7 | Vulkan reports device memory as 16304 MiB, not 16384 — ~80 MiB is driver-reserved | `--list-devices` |
| 8 | Earlier Vulkan numbers exist but are **not** a clean baseline: one arm loaded, one arm failed to start (port collision), 2 rounds × 2 reps, decode 54–60 t/s, acceptance 0.73–0.88, prefill ~570 t/s | `ab_vk.log` from 2026-11-03 |

Note on #8: the failing arm failed on **socket bind**, not on the model. Same
failure class as the zero-acceptance runs retracted in
[MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md). Do not read those rows as a
result.

## 2. The model, and the memory budget

Architecture metadata read from the GGUF header (27B class, IQ3_XXS, hybrid):

| Field | Value |
|---|---|
| Blocks | 65 = 64 main layers + 1 MTP (`nextn_predict_layers = 1`) |
| `full_attention_interval` | 4 → **16** full-attention layers, **48** gated-delta-net layers |
| `attention.head_count` / `head_count_kv` | 24 / 4 |
| `attention.key_length` / `value_length` | 256 / 256 |
| `embedding_length` / `feed_forward_length` | 5120 / 17408 |
| Trained context | 262144 |
| Weights on disk | **9.73 GiB** (866 tensors, includes vocab + MTP block) |

KV grows **only** in the 16 full-attention layers. Per token per layer:
`2 (K+V) × 4 heads × 256 = 2048 elements`.

| KV type | Bytes/token (16 layers) | 120k | 170k | 200k | 300k |
|---|---|---|---|---|---|
| `q4_0` (4.5 b/elem) | 18.0 KiB | 2.11 GiB | 2.98 GiB | 3.52 GiB | 5.26 GiB |
| `q8_0` | 32.0 KiB | 3.75 GiB | 5.31 GiB | 6.25 GiB | 9.38 GiB |
| `f16` | 64.0 KiB | 7.50 GiB | 10.62 GiB | 12.50 GiB | 18.75 GiB |

### The three Vulkan entries as currently configured

| Entry | Device | Context | Slots | KV type | Projector | Coop-matrix opt-in |
|---|---|---|---|---|---|---|
| 27B on the chipset card | `Vulkan0` | 170 000 | 1 | `q4_0` / `q4_0` | Q5_K, 0.32 GiB | set |
| same 27B, "C2" variant | `Vulkan0` | 300 000 | 2 | `q4_0` / `q4_0` | none | **not set** |
| 33B IQ2_M | `Vulkan1` | 100 000 | 1 | `q8_0` / `q4_0` | disabled | **not set** |

All three request `--flash-attn on`, none sets `--fit`, and none leaves the context
unset — so in none of them can the fitter shrink anything (see below).

### Budget against the **15.93 GiB usable** on the card

```
170k / parallel 1 / q4_0 KV, with projector
  weights                      9.73 GiB
  KV @170k                     2.98 GiB
  vision projector (Q5_K)      0.32 GiB
  GDN recurrent state          tens of MiB per slot (confirm from "RS buffer size")
  compute buffers + graphs     0.5 – 2.2 GiB   (wide range: must be measured)
  ────────────────────────────────────────
                               13.6 – 15.3 GiB   vs 15.93 GiB  → fits

300k / parallel 2 / q4_0 KV, no projector
  weights                      9.73 GiB
  KV @300k                     5.26 GiB
  2 slots of recurrent state   ~0.1 GiB
  compute buffers (2 slots,
    300k context)              1.5 – 2.5 GiB
  ────────────────────────────────────────
                               16.6 – 17.6 GiB   vs 15.93 GiB  → does not fit
```

**Verdict.** The 170k configuration is resident by design, with 0.6–2.4 GiB of
margin; the margin is thin only if compute buffers land at the top of their range,
which is precisely what the probe should measure. The 300k / parallel-2 configuration
is over budget by 0.7–1.7 GiB and **cannot** fit on a 16 GiB card at any KV
quantization — even `q4_0` KV leaves no room for two slots' compute buffers. That
entry, not the 170k one, is where "partial offload to RAM" is the right description.

Two consequences worth stating plainly:

- `--fit` cannot rescue an explicitly-set `--ctx-size`. If the context is pinned on
  the command line, the fitter has nothing to shrink; the allocation either fails or
  falls back. To get automatic fitting, the context must be left unset.
- Both cards are the same size, so moving a too-large configuration to the
  CPU-attached card does **not** make it fit. It only changes how painfully the
  spill performs (x2 Gen3 vs x16 Gen4).

## 3. Why prefill is slower on Vulkan here, and why it is not a memory story

The 48 GDN layers are the bulk of this model. On Vulkan they execute as a
per-token serial recurrence over **f32** tensors. On the HIP path the same layers
use chunked kernels that run on the RDNA4 matrix units, including a bf16 variant.
Serial recurrence means prefill work per layer scales linearly with prompt length
with no parallelism across the sequence; chunking parallelizes it.

That predicts exactly what was measured: prefill ≈570 t/s on Vulkan against
≈970 t/s on the HIP path, with decode much closer (54–60 vs ~70 t/s). A memory
placement difference does not produce that shape of result — a compute-structure
difference does.

The all-f32 requirement also inflates compute buffers on those 48 layers, which is
why the free-VRAM margin on this model is thinner under Vulkan than the weights
alone suggest.

## 4. PCIe: the card really is behind a slow bridge

Enumerated topology, both cards:

| Card | Path | Negotiated locally | Effective ceiling |
|---|---|---|---|
| Chipset-attached (`Vulkan0`) | root port → chipset downstream ports → card | x16 Gen4 | **x2 Gen3** at the chipset uplink ≈ 1.6–2.0 GB/s usable |
| CPU-attached (`Vulkan1`) | CPU root complex → switch → card | x16 Gen4 | x16 Gen4 end to end |

The GPU reports x16 Gen4 because that is what it negotiates with the switch directly
below it; the narrow chipset uplink is upstream of that switch and is what actually
bounds host↔device traffic. Weight *loading* is slow on this card. Decode is not
affected **as long as nothing crosses the bridge per token**.

That last clause is what makes FA and CPU-assigned ops dangerous here: a fused op
that lands on CPU is not merely slower per se, it moves data across a ~2 GB/s link on
every token.

## 5. Ranked actions

1. **Do not chase KV placement for the 170k entry.** Confirm residency from the load
   log instead (see the probe below), then move on.
2. **Fix the 300k / parallel-2 entry**: it is over budget. Either lower context to
   ~200k (KV 5.26 → 3.52 GiB, which brings the total under the ceiling), or drop to
   one slot, or split across both cards. Expect a real speed change here, because
   this is the one configuration that actually spills. Dropping the projector is not
   an option here — that entry already has none.
3. **Set flash attention explicitly and verify it stayed on.** `auto` can turn it
   off; the log line `… enabled` / `… not supported, set to disabled` is the only
   evidence. A configuration that "has `--flash-attn on`" and a configuration whose
   FA is actually running are not the same thing.
4. **For prefill-heavy work on this hybrid model, prefer the HIP backend.** The GDN
   gap is structural; no environment variable closes it.
5. **Make the coop-matrix environment consistent across entries.** One entry sets the
   RADV cooperative-matrix opt-in, others do not. Whether the newer self-built Mesa
   enables it by default is *unverified* — measure before assuming.
6. **Check for the degraded-driver state before trusting any Vulkan number.** A
   previously observed transient state made prefill ~4.7× slower and cleared only on
   reboot. If a Vulkan number looks absurdly bad, reboot before analyzing it.

## 6. What is still unmeasured

Stated as gaps, because several of them have previously been filled by assumption
and then corrected:

- No controlled Vulkan-vs-HIP A/B on the *same* card, same model, same context, same
  repetition count. The existing Vulkan rows come from a run whose comparison arm
  never started.
- `RS buffer size`, `KV buffer size`, `model buffer size`, and compute-buffer sizes
  for the Vulkan path are **not** captured anywhere. The budget above is arithmetic
  from GGUF metadata, not a measured allocation report.
- Whether cooperative matrix is active *without* the RADV opt-in under the newer Mesa.
- Whether FA stays enabled when requested explicitly rather than via `auto`.
- Whether the 300k entry currently fails to start, spills, or silently shrinks —
  i.e. whether it is serving at all today.
- The Vulkan GDN cost itself, isolated: it has not been measured by toggling the
  fused GDN op.

## 7. Measurement plan

Run order matters: each arm needs the card to itself, and both cards are currently
occupied by live sessions. The probe script is
[`../perf-bench/vk_mem_probe.sh`](../perf-bench/vk_mem_probe.sh); it captures
allocation placement and fused-op status without needing a benchmark.

| Arm | Purpose | Notes |
|---|---|---|
| P0 residency probe | Prove resident vs spilled for the live 170k config | log capture only, no timing |
| P1 fit ceiling | Find the largest context that stays resident | `--fit` with context unset, then binary-search |
| A1 Vulkan, FA explicitly on | Does FA survive the probe | compare log line, then time |
| A2 Vulkan, FA off | Bound the FA contribution | |
| A3 HIP, same model/ctx/card | The backend comparison that was never done | use the tuned allocator headroom from the MTP notes |
| A4 fused-GDN off | Isolate the GDN cost | if the flag exists in this build |
| A5 coop-matrix opt-in on/off | Settle item 5 | |
| A6 300k entry, as-configured vs at 200k | Quantify the spill penalty over x2 Gen3 | the one arm that tests the user's original hypothesis |

Methodology, per the corrections in [MTP_TUNING_2026-11-03.md](MTP_TUNING_2026-11-03.md):
nonce at the **start** of the prompt, repetitions ≥ 5 (prefill moved 667 → 971 t/s
between 3 and 5 reps on this hardware), acceptance rate recorded alongside decode
throughput, and every arm's engine version and server flags recorded in the result
row. A load failure is a harness failure, not a measurement.
