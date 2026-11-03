# Test suites

A suite is a json file: `{"description": "...", "cases": {"name": {spec}}}`.
Case specs:

- `{"type": "health"}`
- `{"type": "prefill", "sweep_values": [512, 2048]} or "tokens": 2048}` - prompt processing
- `{"type": "decode", "sweep_values": [1024, 8192], "tokens": 128}` - generation at context depth
- `{"type": "kv-cache", "prefix_tokens": 8192, "hits": 3, "tokens": 32}` - prompt-cache speedup
- `{"type": "spec-decode", "prompt_tokens": 8000, "tokens": 1024, "reps": 3, "cache": "warm"}` -
  long-context decode with speculative decoding accounted for. Emits four rows:
  `prefill_tps` (cache-cold, front nonce, generation suppressed), `decode_tps`
  (cache-warm, byte-identical prompt, median of `reps`), `mtp_acc` (accepted draft
  tokens / drafted tokens) and the spread of each. Use this - not plain `decode` -
  whenever drafter settings are in play: `--spec-draft-n-max` / `--spec-draft-p-min`
  change acceptance and per-step cost together, so decode tok/s alone is not a
  comparison. `cache: "cold"` re-busts the cache on every decode rep.

`chars_per_token` (default 4) tunes prompt length. `sweep_values` may be replaced by CLI
`--pp-sizes` / `--depths`; `--prompt-tokens` overrides the spec-decode prompt size.
Select with `--tests myfile.json` or `--tests prefill,decode`.

### Cache semantics (read before trusting a prefill number)

llama.cpp matches the prompt cache from token 0. A nonce at the **end** of a prompt
leaves the whole prefix cached, so the "prefill" measured afterwards is a cache
hit - it can be an order of magnitude faster than the real thing and it is not
reproducible. `lib/prompt.py` therefore puts the nonce at the **front**, and the
`spec-decode` case asserts `cache_n` on every cold rep: if more than 20% of the
prompt was served from cache the run is flagged (`cache_bust=False`) instead of
being averaged in.
