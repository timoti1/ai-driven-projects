# Baseline snapshot — 13 October 2026

Raw output of the model sweep that predates [`../../perf-bench`](../../perf-bench),
kept as a historical record. **Do not use it as an A/B reference.** The analysis of
why, including one methodology bug that turned out to be latent rather than
corrupting, is in
[MTP_TUNING_2026-11-03.md § Why the October snapshot is not comparable](../MTP_TUNING_2026-11-03.md#why-the-october-snapshot-is-not-comparable).

## Files

| file | contents |
|---|---|
| `before.json` | 10 models, one measurement each (4 rows are `null` — the model failed to load or timed out) |
| `after.json` | same sweep re-run later the same day, after tuning (3 rows `null`) |
| `meta.json` | per-model intrinsic properties only: arch, quant, size, ctx, device, layer/KV/FFN shape |

Row schema: `model`, `ctx`, `prompt_tokens`, `prompt_tps`, `gen_tokens`, `gen_tps`,
`cached_tokens`, `wall_s`, `kv_mib`, `kv_per_tok`, `vram_used_mib`, `vram_free_mib`,
`total_mib`.

Local absolute paths in `meta.json` were replaced with `<models>/` and `<home>/`
placeholders when this snapshot was committed; nothing else was altered.

## Why the numbers cannot be reused

- **No engine version and no server flags are recorded.** `meta.json` holds model
  shape and quant, but not the build, batch/ubatch, flash-attn or drafter settings.
  A number here cannot be attributed to any configuration, so it cannot support a
  before/after claim in either direction.
- **One repetition, timed by wall clock.** No spread, so no confidence estimate.
- **Prompt is 4959 tokens.** Decode speed depends strongly on context length (~25 %
  between 2 k and 9 k on the same model), so cross-length comparison is invalid.
- **No speculative-decoding counters.** Decode t/s without an acceptance rate cannot
  distinguish a better drafter from a disabled one.
- **Failures stored as `null` rather than retried**, so the sweep silently covers 6–7
  of 10 models.

Prefill in these runs *was* cache-cold — `cached_tokens = 0` on every measured row —
so the prefill figures are genuine measurements of a cold pass, despite the harness
having a cache-busting bug (nonce at the end of the prompt, which only misleads on a
second pass over the same text).

## Representative rows

| model | device | ctx | prefill t/s | decode t/s |
|---|---|---|---|---|
| 27B IQ3_XXS (Sapphire build) | Vulkan0 | 150000 | 485.7 | 40.7 |
| 27B IQ3_XXS (C2 build) | Vulkan0 | 260000 | 835.3 | 33.8 |
| 27B Swift IQ3_S (C2 build) | Vulkan0 | 220000 | 759.9 | 31.3 |
| 27B IQ3S-Q4 | Vulkan0 | 170000 | 440.6 | 22.0 |
| 27B IQ3_XXS-Q8 | Vulkan0 | 128000 | 419.1 | 46.1 |
| 27B IQ3_XXL (ROCm) | ROCm0 | 140000 | 197.8 | 35.2 |
