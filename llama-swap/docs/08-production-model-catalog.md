# 08. Production model catalog (reference host)

The configs in this repo are modeled on a real two-GPU AMD host
(2x Radeon RX 9070). This page explains what that host actually runs, so you
can steal the patterns for your own machine. Model ids, sources and flags
are taken from `configs/example-two-gpus-production.yaml`.

## Roster

| llama-swap id | Source (Hugging Face) | File/quant | Engine / backend | GPU |
| --- | --- | --- | --- | --- |
| `tiel-coder-35b-a3b` | `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` | Tiel-Coder-35B-A3B-MTP-UD-IQ4_XS.gguf | llama.cpp Vulkan | Gigabyte (Vulkan1) |
| `qwen3.8-27b-IQ3XXS` | `unsloth/Qwen3.8-27B-GGUF` | GSQ-RCO-IQ3_XXS-mtp.gguf | llama.cpp Vulkan | Gigabyte (Vulkan1) |
| `qwen3.8-27b-IQ3XXS-Uncensored` | `RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored` | ...-MTP.gguf + mmproj (vision) | llama.cpp Vulkan | Gigabyte (Vulkan1) |
| `qwen3.8-27b-IQ3S-ROCm` | `unsloth/Qwen3.8-27B-GGUF` | GSQ-RCO-IQ3_S-mtp.gguf | llama.cpp ROCm | Gigabyte (HIP1) |
| `qwen3.8-flash-IQ3_S` | Strata engine configs `strata-iq3_s.json` | Qwen3.8-Flash-Next IQ3_S | custom Python engine (HIP) | Gigabyte (HIP1) |
| `qwen3.8-flash-IQ3_XXS` | Strata engine config `strata-iq3xxs-abl.json` | IQ3_XXS abliterated | custom Python engine (HIP) | Gigabyte (HIP1) |
| `qwen3.8-27b-IQ3XXS-Uncensored-Sapphire` | same uncensored pack | ...-MTP.gguf + mmproj | llama.cpp Vulkan | Sapphire (Vulkan0) |
| `qwen3.8-27b-IQ3XXS-Uncensored-C2` | same pack, v1.1 file | ...-v1.1.gguf, `--parallel 2` | llama.cpp Vulkan | Sapphire (Vulkan0) |
| `qwen3.8-27b-IQ3XXS-Sapphire` | `unsloth/Qwen3.8-27B-GGUF` | twin of the Gigabyte IQ3_XXS | llama.cpp Vulkan | Sapphire (Vulkan0) |
| `qwen3.8-27b-IQ3S-ROCm-Sapphire` | `unsloth/Qwen3.8-27B-GGUF` | twin IQ3_S, re-tuned batches | llama.cpp ROCm | Sapphire (HIP0) |

Everything runs with MTP speculative decoding (`--spec-type draft-mtp`),
flash attention, q4/q8 KV quantization (`-ctk/-ctv`) and tuned sampling
defaults baked into `cmd:`.

## Patterns worth copying

- **One model per GPU, twins per GPU.** Each pack exists on both GPUs
  ("...-Sapphire" twins). Requesting a twin moves work to the other GPU
  with zero swap cost; the matrix `pair` set encodes the allowed
  combinations (doc 04).
- **Same weights, different backends.** IQ3_XXS via Vulkan vs IQ3_S via
  ROCm side by side to benchmark backends on identical hardware.
- **Vision adapters.** `--mmproj` attaches a multimodal projector to an
  otherwise text-only model.
- **Custom engine isolation.** The Strata models use a separate Python
  engine with its own venv and JSON configs; they get `ttl: 86400` (stay
  up) and `evict_costs: 10` (don't bounce them).
- **A second chat instance** (`-C2`, `--parallel 2`, `--ctx-size 300000`)
  serves two users concurrently on one GPU slot.

## Outside llama-swap on that host

- `llama-postscribe.service`: standalone `llama-server` on port 8099 with
  `gemma-4-E2B-it-Q4_K_M` + MTP draft model, CPU-only (`-ngl 0`), always on
  for a small background writing task
- `llama-metrics.service`: sidecar that scrapes `--metrics` from engines

## Getting these models

File names above map to the Hugging Face repos listed; each is
`huggingface-cli download <repo> <file> --local-dir <dir>` or your browser.
Always download the `mmproj-*.gguf` companion if you want image input, and
`-mtp.gguf` draft files only if you enable `--spec-type draft-mtp`.
