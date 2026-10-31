#!/usr/bin/env bash
# update_engines.sh — Update all engine forks from their git remotes and rebuild.
#
# Engines:
#   avalon-hip      — /home/timoti/Avalon (git repo)
#   llama-latest    — /home/timoti/Downloads/llama-latest (git repo)
#   rocmfpx-runtime — /home/timoti/llama-rocmfpx-runtime (git repo? or standalone)
#   strata          — /media/timoti/Data/repos/Strata (git repo)
#
set -uo pipefail

log() { echo "[update] $*"; }

# ── avalon-hip ────────────────────────────────────────────────────────────────
if [[ -d /home/timoti/Avalon/.git ]]; then
    log "Updating Avalon (/home/timoti/Avalon)..."
    cd /home/timoti/Avalon || exit 1
    git pull --ff-only || log "WARN: avalon git pull failed (local changes?)"
    log "Avalon updated. Rebuild if needed (see build instructions)."
else
    log "SKIP: /home/timoti/Avalon is not a git repo"
fi

# ── llama-latest ──────────────────────────────────────────────────────────────
if [[ -d /home/timoti/Downloads/llama-latest/.git ]]; then
    log "Updating llama-latest (/home/timoti/Downloads/llama-latest)..."
    cd /home/timoti/Downloads/llama-latest || exit 1
    git pull --ff-only || log "WARN: llama-latest git pull failed"
    log "llama-latest updated. Rebuild if needed."
else
    log "SKIP: /home/timoti/Downloads/llama-latest is not a git repo"
fi

# ── rocmfpx-runtime ───────────────────────────────────────────────────────────
if [[ -d /home/timoti/llama-rocmfpx-runtime/.git ]]; then
    log "Updating rocmfpx-runtime (/home/timoti/llama-rocmfpx-runtime)..."
    cd /home/timoti/llama-rocmfpx-runtime || exit 1
    git pull --ff-only || log "WARN: rocmfpx-runtime git pull failed"
else
    log "SKIP: /home/timoti/llama-rocmfpx-runtime is not a git repo (standalone binary)"
fi

# ── strata ────────────────────────────────────────────────────────────────────
if [[ -d /media/timoti/Data/repos/Strata/.git ]]; then
    log "Updating Strata (/media/timoti/Data/repos/Strata)..."
    cd /media/timoti/Data/repos/Strata || exit 1
    git pull --ff-only || log "WARN: strata git pull failed"
    log "Strata updated."
else
    log "SKIP: /media/timoti/Data/repos/Strata is not a git repo"
fi

log "Engine update check complete."
