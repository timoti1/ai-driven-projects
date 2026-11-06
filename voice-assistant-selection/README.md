# Voice Assistant Selection

Which voice-assistant host to run on top of the existing local backend, and how to get
**parakeet-class speech-to-text** (Handy's quality) into a **terminal** workflow.

Companion to [voice-slm-selection](../voice-slm-selection/README.md), which settled the *text*
model (Qwen3.5-4B Q4_K_M). This document settles the *speech stack* and the *assistant host*.

## Requirements

| # | Requirement | Why |
|---|---|---|
| R1 | STT = **parakeet-ultra** class (the model Handy uses), not faster-whisper `small` | current Jarvis ASR mangles Russian tech vocabulary |
| R2 | LLM = the existing local endpoints (`llama-swap` `:8080`, Qwen3.5-4B CPU `:5899`) | one backend, already tuned and measured |
| R3 | Works **in terminal apps** (pi / opencode prompts by voice) | Handy currently fails there |
| R4 | Russian + mixed RU/EN dictation | real usage |
| R5 | Low maintenance: no fork, no per-release patching | the stack must survive upgrades |
| R6 | Model file / STT service shared between apps, not duplicated per app | disk is tight (~67 GB) |

## Current state (measured, not assumed)

> Snapshot of the state *before* the changes documented in
> [What was built (2026-11-05)](#what-was-built-2026-11-05) and
> [What was built (2026-11-06)](#what-was-built-2026-11-06).
> Handy now runs `parakeet-ultra-Q4_K_M.gguf` with `paste_method: shift_insert`; Jarvis is removed;
> Cicero is deployed as above.

Handy (`C:\Users\Admin\AppData\Roaming\com.pais.handy\settings_store.json`):

```
selected_model            = handy-computer/parakeet-ultra-gguf/parakeet-ultra-Q8_0.gguf
selected_language         = ru          spoken_languages = [ru, en]
post_process_enabled      = true        provider = custom → http://192.168.1.104:8080/v1
post_process_model        = qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire
paste_method              = direct      reliable_paste = true
keyboard_implementation   = handy_keys  external_script_path = none
```

Jarvis (`C:\Users\Admin\.config\jarvis\config.json`):

```
llm_base_url  = http://192.168.1.104:5899/v1   llm_chat_model = Qwen3.5-4B-Q4_K_M.gguf
whisper_model = small                          tts_engine = piper (ru_RU-dmitri-medium)
dictation_hotkey = ctrl+win
```

So: the *text* half is already right, the *speech* half is split — good STT in a dictation tool
that cannot type into a terminal, and an assistant in a terminal that has bad STT.

## The fact that decides the design

**parakeet-ultra is a GGUF for `transcribe.cpp`** (`github.com/handy-computer/transcribe.cpp`,
MIT, maintained by the Handy team). Handy links `transcribe-cpp` 0.4.x for *every* model it runs.

Consequences:

- **faster-whisper (CTranslate2) and whisper.cpp (GGML-Whisper) cannot load it.** Parakeet is a
  FastConformer encoder + TDT head, not a Whisper decoder. Jarvis's STT cannot be swapped by
  config — only by replacing the code path.
- Anything that wants the *exact same model* must either embed `transcribe.cpp` (C/C++ API +
  **Python / TypeScript / Rust / Swift bindings**) or talk to something that does.
- `transcribe.cpp` ships **no server** — CLI + bindings only. A network service is a thin wrapper.

### Model options (all `transcribe.cpp` GGUF, all CPU-friendly)

| Variant | Params | Languages | Q8_0 | Error rate | Notes |
|---|---:|---|---:|---|---|
| `parakeet-ultra` | 627M | 25 European + auto-detect | 740 MB | 1.80% LibriSpeech | what Handy runs today; internal VAD splits >30 s audio |
| `parakeet-tdt-0.6b-v3` | 627M | 25 European + auto-detect | 740 MB | 1.94% LibriSpeech | upstream of ultra; also ONNX (sherpa-onnx) |
| `orukeet` | 627M | 25 European | 740 MB | 1.86% | CC-BY-SA |
| `gigaam-v3-e2e-rnnt` | 223M | **ru only** | 274 MB | 5.35% FLEURS-ru | 3× smaller, RU-first, cased+punctuated |
| `nemotron-3.5-asr-streaming-0.6b` | 0.6B | multilingual | — | — | **streaming** (low latency), used by Cicero via audio.cpp |
| `whisper-large-v3-turbo` | — | ~99 | ~1.6 GB | — | baseline for comparison |

Language hint is accepted but ignored on the v3 lineage (auto-detect only). Parakeet family does
not translate or diarize. GigaAM is windowed at 25 s internally.

## The interop contract

Everything below speaks **`POST /v1/audio/transcriptions`** (OpenAI Whisper API). That is the seam:
any host that supports an "OpenAI-compatible transcription" provider can consume any parakeet
service, and the STT engine stays swappable without touching the host.

### STT services (sidecars, not assistants)

| Service | Engine | Russian | Platform | Effort |
|---|---|---|---|---|
| **vocalinux-transcribe-cpp-bridge** (`ypavlov/…`) | **transcribe.cpp** — same engine as Handy → can serve `parakeet-ultra` or `gigaam-v3` | yes (tested with GigaAM ru) | Linux (Vulkan/CPU); Windows needs the lib build | low: `server.py` + `TRANSCRIBE_MODEL` env, port 8765 |
| **parakeet-api** (`likeablob/parakeet-api`) | sherpa-onnx (CPU) / MLX | `parakeet-tdt-0.6b-v3` int8 (25 langs) | Windows + Linux, Docker image | very low: `uv tool install parakeet-api`, `download sherpa`, `serve` → `:8816` |
| `chand1012/parakeet-server` | Parakeet TDT v3 | yes (v3 langs) | Docker | low |
| `tems-ai/temsai-asr-server` | Parakeet TDT | v3 langs | Docker, CPU/NVIDIA, per-word confidence | low |
| `psyb0t/docker-talkies` | multiple | depends | Docker; also WS live ASR + TTS + MCP | low |
| `izwi` (`izwi-ai/izwi`) | own runtime: Parakeet, Whisper, Qwen3-ASR, Nemotron, Granite + TTS + local chat | v3 langs | Win/Linux/macOS (Win/Linux CPU) | low, but it is a whole app |
| sherpa-onnx `websocket`/`http` server | sherpa-onnx | v3 + GigaAM ONNX | cross-platform | medium (DIY) |
| whisper.cpp `server` | whisper.cpp | whisper only | cross-platform | n/a for R1 |

`parakeet-api` ignores `model`/`language` (single model per process) and adds a `hotwords`
extension — useful for `llama-swap`, `matview`, `ROCm`-style vocabulary.

### Assistant hosts

| Host | LLM backend | STT | Terminal use | Platform | Verdict |
|---|---|---|---|---|---|
| **Handy** | post-process only (OpenAI-compat) | **parakeet-ultra** (transcribe.cpp) | paste into focused window — **broken today** (`paste_method=direct`) | Win/mac/Linux | keep as dictation front-end, not an assistant |
| **Jarvis** (current) | OpenAI-compat ✅ | faster-whisper ❌ (R1 impossible) | wake-word, always-on, clipboard paste | Win/WSL | only if STT is replaced by a sidecar call (patch `src/jarvis/listening/`) |
| **Cicero** (`5uck1ess/cicero`) | `openai`/`llama-cpp`/`ollama` **baseUrl** ✅, ACP agents, claude-code/codex/gemini/qwen | faster-whisper, audio.cpp **Nemotron 3.5 ASR streaming**, MLX, **Wyoming**, cloud; `stt.host` may point at a remote server; `cicero swap stt …` at runtime | **best**: tmux/kitty/wezterm tab-inject, `cicero hook` (agent Stop hooks), `cicero scrape <tab>`, `cicero dictate`, web voice page + phone pairing | Linux (CUDA), macOS 14+, **Windows documented** (Bun + scoop) | **best terminal-native candidate** |
| **AnythingLLM** Desktop | Generic OpenAI ✅ | **Generic OpenAI** `/v1/audio/transcriptions` ✅ → parakeet sidecar | no (own chat UI) | Win/mac/Linux desktop + Docker | easiest R1+R2 combo, wrong UX for pi |
| **Open WebUI** | OpenAI-compat ✅ | `AUDIO_STT_ENGINE=openai` + `AUDIO_STT_OPENAI_API_BASE_URL` ✅ | no (web UI) | Docker | same as above, heavier; realtime calls need an OpenAI realtime server |
| **OpenClaw** | gateway + providers, ACP | node-side speech (Apple/Android), OpenAI realtime bridge pinned to OpenAI | gateway/CLI, not dictation-into-terminal | Windows Hub app, Windows node, WSL2 gateway | powerful, wrong shape for R1/R3 |
| **Izwi** | own local chat models + `/v1/chat/completions` | Parakeet/Whisper/Qwen3-ASR/Nemotron + Kokoro/Qwen3-TTS, OpenAI-compat routes | none (app/UI) | Win/mac/Linux | better as the **speech service** than as the assistant |
| HA Assist / Wyoming, Willow, GLaDOS, VoiceStar, Leon | varies | mostly whisper/Vosk | room/hardware voice, not terminal typing | varies | not for a coding-terminal loop |

## Why Handy fails in terminals (R3) — and the fix

From Handy's own docs (`handy.computer/docs/paste-methods.html`) and issues:

- **`paste_method = direct` types character-by-character and ignores non-US keyboard layouts.**
  With `selected_language = ru` this is exactly the wrong method. Issue **#692**: *Direct repeats
  and breaks text when typing into terminals (Codex/Claude Code)*. Issue **#918**: *doesn't paste
  into Windows CMD terminal running Codex CLI*.
- Docs: **Shift+Insert is the recommended method for Windows Terminal / CMD / PowerShell**;
  `Ctrl+V` is intercepted differently there. `reliable_paste = true` only applies to clipboard
  methods, so today it does nothing.
- Windows UIPI: a non-elevated Handy cannot send input to an elevated terminal — run both at the
  same elevation.
- Values in `settings_store.json`: `paste_method` ∈ `ctrl_v | ctrl_shift_v | shift_insert | direct | none | external_script`;
  `keyboard_implementation` ∈ `tauri | handy_keys | none`; `external_script` paste is **Linux only**.

Fix order (no code, minutes): `paste_method → shift_insert`; keep `reliable_paste`; raise
`paste_delay_ms` to 120–200 if the old clipboard leaks through; if the hotkey itself is swallowed,
try `keyboard_implementation = tauri`; check terminal elevation.

## Can transcription be delegated to Handy?

Partly, and it is the cheapest path to R1:

- **Trigger from anywhere:** `handy --toggle-transcription`, `handy --toggle-post-process`,
  `handy --cancel` are handled by the running instance on all platforms. Bind them in Windows
  Terminal `keybindings.json`, a AutoHotkey script, or `tmux bind-key -c` — so a terminal key
  starts/stops Handy recording.
- **Rewrite/route the text before paste:** `hooks/transcription` in Handy's app-data folder —
  stdin = transcript (post-LLM), stdout = what gets pasted. **macOS and Linux only.** On Windows
  there is no hook and no HTTP API, so the text can only reach the terminal by typing/paste.
- Practical WSL route: run Handy **inside WSL2** (Linux `.deb`) with `keyboard_implementation =
  handy_keys` + `typing_tool = ydotool`, then the Linux hook can write straight into the pi pane
  (`tmux load-buffer … ; paste-buffer`, or `wtype`). That gives parakeet-ultra → pi with no
  Windows paste path at all.

## Recommended architecture

Two hosts share one speech service; nothing duplicates the model per app.

```
                        mic
                         │
         ┌───────────────▼─────────────────────────────┐
         │ STT service — one process, ryzen5800        │
         │ transcribe.cpp + parakeet-ultra-Q8_0.gguf   │
         │ (or gigaam-v3-e2e-rnnt for RU-only speed)   │
         │ POST /v1/audio/transcriptions  :8765        │
         └───────┬──────────────────────┬──────────────┘
                 │                      │
   Handy (dictation, Windows)     Cicero (voice agent, WSL2)
   paste method = shift_insert    stt → :8765, terminal: tmux
                 │                tab-inject → pi pane
                 │                      │
                 └──────────┬───────────┘
                            ▼
          llama-swap :8080  — qwen3.8-27b, transcript post-process
          Qwen3.5-4B  :5899 — front desk / helper
```

Phases:

1. **Fix Handy in the terminal** (`shift_insert`). Zero risk, unblocks voice→pi today with
   parakeet-ultra already in place. Acceptance: 10 dictated Russian prompts land intact in pi.
2. **Stand up one STT service.** Fastest: `parakeet-api` (sherpa-onnx, `parakeet-tdt-0.6b-v3`
   int8) on `:8816`. Best-quality/same-file: the `transcribe.cpp` bridge with the *same*
   `parakeet-ultra-Q8_0.gguf` on `:8765`. Acceptance: `curl -F file=@test.wav` returns the same
   text Handy produces; RU tech terms correct.
3. **Pick the terminal host = Cicero** (`stt.backend` pointed at the service, `llm.baseUrl` →
   `:8080`/`:5899`, `terminal: tmux`, pi running in a tmux pane; `cicero hook` for agent replies).
   Keep AnythingLLM/Open WebUI only if a chat-window assistant is wanted — both accept the same
   STT service through their OpenAI-compatible transcription provider.
4. **Jarvis**: retire, or patch its listening module to POST to the STT service (one module,
   ~50 lines) if wake-word room listening must stay.

## What was built (2026-11-05)

The plan above is implemented. What actually changed on each machine, with measured numbers.

### Parakeet quant (the R1 model)

`transcribe.cpp` benchmark, CPU 8 threads, 3 RU samples × {clean, SNR10} (9 runs each):

| Quant | clean RTF | snr RTF | clean WER | clean CER | size |
|---|---:|---:|---:|---:|---:|
| `parakeet-ultra-Q8_0` | 0.057 | 0.054 | 12.3 | 8.8 | 740 MB |
| `parakeet-ultra-Q5_K_M` | 0.042 | 0.042 | 12.3 | 8.8 | 549 MB |
| `parakeet-ultra-Q4_K_M` | 0.044 | 0.041 | 12.3 | 8.8 | 486 MB |

WER/CER are identical across quants; transcripts match except one capitalization (`config` →
`Config`) in the llama-swap sample, where Q8_0 lowercases the tech term and Q4/Q5 capitalize it.
Q4_K_M is 35% smaller than Q8_0 and ~25% faster, at the same accuracy. **Chosen: Q4_K_M** for both
the server and Handy.

### STT service (one process, shared)

- `~/voice-backend/stt_parakeet_server.py` — `transcribe.cpp` over `parakeet-ultra.gguf` (Q4_K_M,
  `~/models/parakeet/`, 486 MB). OpenAI-compatible `POST /v1/audio/transcriptions` + `GET /health`,
  ffmpeg decode, CPU 8 threads, port **8002**.
- systemd user service `voice-stt-parakeet` (enabled), ~650 MB RSS.
- Serves both Handy (via the shared GGUF) and Cicero (via `stt.host`).

### Cicero (terminal voice agent)

- `~/cicero` (Bun, 287 packages). Config `~/.cicero/config.yaml`:
  - brain (front desk) → `http://127.0.0.1:5899/v1`, model `Qwen3.5-4B`
  - `stt.backend: faster-whisper`, `host: 192.168.1.104`, `port: 8002` (the parakeet service)
  - `tts.backend: kokoro`, `host: 192.168.1.104`, `port: 8003`, `voice: irina` (the Piper service)
  - `terminal: tmux`, `privacy: local` with `allow: [speech]`
- **Adoption, not spawn:** Cicero's `faster-whisper` and `kokoro` providers reuse an already-running
  server when its health URL answers (`/health` for STT, `/v1/models` for TTS) instead of spawning a
  local venv. Pointing `stt.host`/`tts.host` at the LAN IP therefore reuses the existing parakeet and
  Piper services — no second model copy, no GPU.
- Added `GET /v1/models` to the Piper server (`tts_server.py`) so the `kokoro` health check passes;
  its `POST /v1/audio/speech` already returned WAV, matching the `kokoro` request shape.
- `cicero doctor`: **0 fail / 0 warn**.

### Jarvis

Removed from both machines — Windows `D:\Install\jarvis`, `%LOCALAPPDATA%\jarvis`,
`~/.config/jarvis`; server `~/.config/jarvis`, `~/.local/share/jarvis`. No startup entries, no
processes. Freed ~1.2 GB.

### Handy (dictation front-end)

- `selected_model` → `handy-computer/parakeet-ultra-gguf/parakeet-ultra-Q4_K_M.gguf` (486 MB,
  SHA256 `c69b7a5f…`, byte-identical to the HF LFS blob). Q8_0 kept as a fallback.
- `paste_method: shift_insert`, `paste_delay_ms: 120` (the R3 terminal fix).

### End-to-end (measured)

- STT (parakeet :8002): clean RU transcript on a real sample.
- brain (Qwen3.5-4B :5899): ~2.6 s for a short voice reply.
- TTS (Piper :8003, `irina`): valid WAV, ~0.5 s.

### Resulting layout

```
  mic ─┬─ Handy (Windows, parakeet Q4_K_M) ── shift_insert paste ──▶ terminal
       └─ Cicero (server) ─ parakeet :8002 ─ Qwen3.5-4B :5899 ─ Piper irina :8003 ─▶ speaker
```

## What was built (2026-11-06)

Follow-up to the 11-05 deployment: the helper model, the TTS voice, and a thinking-leak fix.

### Helper model → Qwen3.5-4B (was avalon-qwen3.8-flash-next :8080)

Cicero's `llm` (intent) and `web_voice.tldr.summarizer` (long-reply summary) both pointed at the
125B `avalon-qwen3.8-flash-next` on `:8080` — heavy to load, slow to start. Both now point at
**Qwen3.5-4B on `:5899`** (already running, fast on CPU, enough for intent + one-line summaries).
No more 125B dependency in the voice loop:

```
llm.baseUrl                  = http://127.0.0.1:5899/v1   model Qwen3.5-4B
web_voice.tldr.summarizer_url = http://127.0.0.1:5899/v1   model Qwen3.5-4B
```

### TTS → kokoro-ru (higher-quality Russian)

Piper `irina` (11-05) was found low quality. Added **kokoro-ru** (Apache-2.0, 82 M params,
non-autoregressive → fast on CPU, ~2.50% WER vs Piper's 4.38%):

- `~/kokoro-ru/` — ONNX `model_quantized.onnx` (sveta/masha) + `model_dima_quantized.onnx` (dima),
  voice packs `sveta.bin` / `masha.bin` / `dima.bin` (510 KB each), `config.json` (114-char phoneme
  vocab), a `.venv` with onnxruntime.
- G2P via `espeak-ng -v ru --ipa=3` → normalize → vocab map (100% coverage; no RUAccent dependency
  chain).
- Wired into `tts_server.py` behind the same `:8003` port: `sveta` / `masha` / `dima` route to
  kokoro-ru; `dmitri` / `irina` / `denis` / `ruslan` still route to Piper. `voice: sveta` in
  `~/.cicero/config.yaml`.
- kokoro-ru RTF ~0.10 on CPU (8 threads).

### Thinking-leak fix (`/no_think` + context-restore + TTS strip)

Qwen3.5-4B is a thinking model. With `llama-server -rea off` it still verbalized its reasoning as
plain text — every reply opened with "Hmm, thinking", "Let me see", "Give me a second", "One
moment" — and TTS spoke all of it. Three layers, because one wasn't enough:

1. **`/no_think` in the server system prompt** (`~/.local/state/qwen35-4b-cpu/system_prompt.txt`) —
   stops the habit on fresh prompts, but not in a live conversation.
2. **Context-restore priming (the real cause).** On daemon restart Cicero sends a
   "Context restore after a restart" message that recaps the recent conversation — including the
   model's own past dirty replies — and says "carry on as if there was no interruption." The model
   imitated that recap's style, so the filler came back. Clearing `~/.cicero/web-voice/history.jsonl`
   removes the dirty recap; with clean replies accumulating, the recap stays clean.
3. **TTS-side strip (safety net).** `tts_server.py` `_clean()` now calls `_strip_filler()`, which
   drops leading filler phrases ("Give me a second", "One moment", "Hmm, thinking", etc.) before
   synthesis. So even if the model ever generates filler again, it's never spoken.

### Resulting layout

```
  mic ─┬─ Handy (Windows, parakeet Q4_K_M) ── shift_insert paste ──▶ terminal
       └─ Cicero (server) ─ parakeet :8002 ─ Qwen3.5-4B :5899 (brain + llm + tldr)
                                          └─ kokoro-ru sveta :8003 ─▶ speaker
```

## Sharing the model between Handy and the assistant

- **Same file, yes.** Handy loads GGUFs from `%APPDATA%\com.pais.handy\models` **and** from the
  shared HF cache (`~/.cache/huggingface/hub/models--handy-computer--parakeet-ultra-gguf`).
  Point `TRANSCRIBE_MODEL` at that same path; the sidecar reads the identical file.
- **RAM is shared too on CPU**: `transcribe.cpp` mmaps weights into the page cache, so Handy and
  the sidecar do not each hold a private copy (don't rewrite the GGUF in place while loaded).
- **Not shared**: GPU/Vulkan arenas (one device context per process) and `transcribe.cpp`'s
  one-compute-call-per-model lock — run one service process, let clients hit it over HTTP.
- sherpa-onnx (`parakeet-api`) needs **ONNX**, so it uses its own model dir; that is a second
  ONNX download (int8, a few hundred MB), not a second copy of the GGUF.

## Open questions / next experiments

- [x] Parakeet quant A/B (`Q8_0` / `Q5_K_M` / `Q4_K_M`): identical WER/CER, Q4_K_M 35% smaller and
      ~25% faster → **Q4_K_M** shipped (see [What was built](#what-was-built-2026-11-05)).
- [x] `transcribe.cpp` Python binding usable without a local build: yes — `stt_parakeet_server.py`
      runs on the `transcribe_cpp` wheel in `~/voice-backend/.venv-parakeet`.
- [x] Cicero + tmux tab-inject: deployed on the Linux server; pi runs in a tmux pane, `terminal: tmux`.
- [x] Latency budget: parakeet RTF ~0.04 on CPU (well under real time), so offline is fine for now.
- [x] Helper model: `avalon-qwen3.8-flash-next` :8080 → Qwen3.5-4B :5899 for `llm` + `tldr`
      (see [What was built (2026-11-06)](#what-was-built-2026-11-06)).
- [x] TTS voice: Piper `irina` → kokoro-ru `sveta` (see [What was built (2026-11-06)](#what-was-built-2026-11-06)).
- [ ] kokoro-ru voice A/B: `sveta` vs `masha` vs `dima` — which sounds best for RU dictation?
- [ ] Does `shift_insert` fully fix pi-in-Windows-Terminal, or is the *hotkey* also lost
      (then test `keyboard_implementation = tauri`, then the CLI-flag trigger)? Applied; pending a
      live 10-prompt dictation check.
- [ ] WER A/B on real dictation: `parakeet-ultra` vs `gigaam-v3-e2e-rnnt` vs `parakeet-tdt-0.6b-v3`
      (sherpa-onnx) on the 12 messy cases from `voice-slm-selection/data/cases.json` audio.
- [ ] Russian quality of `parakeet-api` v3 int8 vs GGUF ultra — is the ONNX port lossy?
- [ ] If sub-second partials matter, test `nemotron-3.5-asr-streaming-0.6b` (streaming) instead of
      the offline parakeet.

## Sources

- transcribe.cpp: `github.com/handy-computer/transcribe.cpp` (README, `docs/models/parakeet.md`,
  `docs/models/gigaam.md`, `bindings/python/README.md`); Rust crate `transcribe-cpp` 0.4.x.
- Handy: `github.com/cjpais/Handy` README + `handy.computer/docs/paste-methods.html`,
  issues #918, #692, #502; `src-tauri/src/settings.rs` (`PasteMethod`, `KeyboardImplementation`).
- Cicero: `github.com/5uck1ess/cicero`, `5uck1ess.github.io/cicero` (setup, brains, terminal
  adapters, remote model servers).
- AnythingLLM: `docs.anythingllm.com/features/transcription-models` (Generic OpenAI STT),
  `/features/text-to-speech` (Piper, Kokoro, OpenAI-compatible).
- Open WebUI: `docs.openwebui.com` STT env vars (`AUDIO_STT_ENGINE`, `AUDIO_STT_OPENAI_API_BASE_URL`).
- parakeet-api: `github.com/likeablob/parakeet-api`. sherpa-onnx NeMo model list:
  `k2-fsa.github.io/sherpa/onnx/nemo/index.html`.
- Sidecars: `ypavlov/vocalinux-transcribe-cpp-bridge`, `chand1012/parakeet-server`,
  `tems-ai/temsai-asr-server`, `psyb0t/docker-talkies`, `izwi-ai/izwi`.
