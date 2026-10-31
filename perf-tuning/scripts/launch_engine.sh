#!/usr/bin/env bash
# launch_engine.sh — Start a specific llama-server engine on a specific ROCm/Vulkan backend.
#
# Usage:
#   launch_engine.sh <engine_name> <port> <parallel> [extra_llama_args...]
#
# Engines (defined in ENGINE_MAP below):
#   avalon-hip      — /home/timoti/Avalon/build/bin/llama-server  (llama.cpp 0.26.0, HIP/ROCm)
#   llama-latest-vulkan — /home/timoti/Downloads/llama-latest/build/bin/llama-server  (llama.cpp 0.24.0, Vulkan)
#   rocmfpx-vulkan  — /home/timoti/llama-rocmfpx-runtime/llama-server  (LaurentZuijdwijk b10641, Vulkan)
#   strata          — /media/timoti/Data/repos/Strata/engine/strata (Strata proprietary, HIP)
#
# Environment:
#   ROCM_VERSION    — 7.8.0 | 7.13 | 7.2.4  (selects LD_LIBRARY_PATH)
#   HIP_VISIBLE_DEVICES — 0 (Sapphire/PCIe x2) | 1 (Gigabyte/PCIe x16)
#   VK_DRIVER_FILES — path to Vulkan ICD JSON (for Vulkan backends)
#
set -uo pipefail

ENGINE_NAME="${1:?Usage: launch_engine.sh <engine_name> <port> <parallel> [extra args]}"
PORT="${2:?Missing port}"
PARALLEL="${3:?Missing parallel}"
shift 3
EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Engine definitions ────────────────────────────────────────────────────────
declare -A ENGINE_BIN
declare -A ENGINE_MODEL
declare -A ENGINE_MTP
declare -A ENGINE_ENV_PRE

ENGINE_BIN[avalon-hip]="/home/timoti/Avalon/build/bin/llama-server"
ENGINE_MODEL[avalon-hip]="/media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf"
ENGINE_MTP[avalon-hip]="/media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf"
ENGINE_ENV_PRE[avalon-hip]="CUDA_VISIBLE_DEVICES="

ENGINE_BIN[llama-latest-vulkan]="/home/timoti/Downloads/llama-latest/build/bin/llama-server"
ENGINE_MODEL[llama-latest-vulkan]="/media/timoti/Data/lmstudio/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf"
ENGINE_MTP[llama-latest-vulkan]=""
ENGINE_ENV_PRE[llama-latest-vulkan]="CUDA_VISIBLE_DEVICES="

ENGINE_BIN[rocmfpx-vulkan]="/home/timoti/llama-rocmfpx-runtime/llama-server"
ENGINE_MODEL[rocmfpx-vulkan]="/media/timoti/Data/lmstudio/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf"
ENGINE_MTP[rocmfpx-vulkan]=""
ENGINE_ENV_PRE[rocmfpx-vulkan]=""

ENGINE_BIN[strata]="/media/timoti/Data/repos/Strata/engine/strata"
ENGINE_MODEL[strata]="/media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf"
ENGINE_MTP[strata]="/media/timoti/Data/Strata-data/mtp/alt/mtp-q8_0.gguf"
ENGINE_ENV_PRE[strata]=""

# ── Validate engine ───────────────────────────────────────────────────────────
if [[ -z "${ENGINE_BIN[$ENGINE_NAME]:-}" ]]; then
    echo "ERROR: unknown engine '$ENGINE_NAME'. Available: ${!ENGINE_BIN[*]}"
    exit 1
fi

BIN="${ENGINE_BIN[$ENGINE_NAME]}"
MODEL="${OVERRIDE_MODEL:-${ENGINE_MODEL[$ENGINE_NAME]}}"
MTP="${OVERRIDE_MTP:-${ENGINE_MTP[$ENGINE_NAME]}}"
ENV_PRE="${ENGINE_ENV_PRE[$ENGINE_NAME]}"

if [[ ! -x "$BIN" && ! -f "$BIN" ]]; then
    echo "ERROR: engine binary not found: $BIN"
    exit 1
fi
if [[ ! -f "$MODEL" ]]; then
    echo "ERROR: model file not found: $MODEL"
    exit 1
fi

# ── ROCm version selection ────────────────────────────────────────────────────
case "${ROCM_VERSION:-7.8.0}" in
    7.8.0)
        export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"
        ;;
    7.13)
        export LD_LIBRARY_PATH="/opt/rocm/core-7.13/lib:${LD_LIBRARY_PATH:-}"
        ;;
    7.2.4)
        export LD_LIBRARY_PATH="/home/timoti/rocm724-portable/lib:${LD_LIBRARY_PATH:-}"
        ;;
    *)
        echo "WARNING: unknown ROCm version '${ROCM_VERSION}', using system defaults"
        ;;
esac

# ── Vulkan ICD ────────────────────────────────────────────────────────────────
if [[ -n "${VK_DRIVER_FILES:-}" ]]; then
    export VK_DRIVER_FILES
elif [[ "$ENGINE_NAME" == *vulkan* && -f /home/timoti/mesa-build/radeon_icd.json ]]; then
    export VK_DRIVER_FILES="/home/timoti/mesa-build/radeon_icd.json"
fi

# ── HIP device selection ──────────────────────────────────────────────────────
export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-1}"

echo "=== Launching engine: $ENGINE_NAME ==="
echo "  Binary:    $BIN"
echo "  Model:     $MODEL"
echo "  Port:      $PORT"
echo "  Parallel:  $PARALLEL"
echo "  ROCm:      ${ROCM_VERSION:-system}"
echo "  HIP_DEV:   $HIP_VISIBLE_DEVICES"
echo "  VK_DRIVER: ${VK_DRIVER_FILES:-<default>}"
echo "  LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo

# ── Kill anything on this port ────────────────────────────────────────────────
fuser -k "${PORT}/tcp" 2>/dev/null || true
sleep 2

# ── Build command ─────────────────────────────────────────────────────────────
case "$ENGINE_NAME" in
    avalon-hip)
        CMD=(
            "$BIN"
            -m "$MODEL"
            -c 200000
            -b 4096
            -ub 2048
            -fa on
            -ctk q8_0 -ctv q4_0
            --jinja
            --parallel "$PARALLEL"
            -md "$MTP"
            --spec-type draft-mtp
            --spec-draft-n-max 3
            -ubd 256
            -ctkd q8_0 -ctvd q4_0
            --temp 0.6 --top_k 30 --top-p 0.95
            --reasoning-effort low --reasoning-budget 4092
            --host 0.0.0.0
            --port "$PORT"
            --metrics
        )
        ;;
    llama-latest-vulkan)
        CMD=(
            "$BIN"
            -m "$MODEL"
            -c 200000
            -b 4096
            -ub 2048
            -fa on
            -ctk q8_0 -ctv q4_0
            --jinja
            --parallel "$PARALLEL"
            --spec-type draft-mtp
            --spec-draft-n-max 3
            --temp 0.6 --top_k 30 --top-p 0.95
            --reasoning-effort low --reasoning-budget 4092
            --host 0.0.0.0
            --port "$PORT"
            --metrics
            "${EXTRA_ARGS[@]}"
        )
        ;;
    rocmfpx-vulkan)
        CMD=(
            "$BIN"
            -m "$MODEL"
            -c 200000
            -b 4096
            -ub 2048
            -fa on
            -ctk q8_0 -ctv q4_0
            --jinja
            --parallel "$PARALLEL"
            --spec-type draft-mtp
            --spec-draft-n-max 3
            --temp 0.6 --top_k 30 --top-p 0.95
            --reasoning-effort low --reasoning-budget 4092
            --host 0.0.0.0
            --port "$PORT"
            --metrics
            "${EXTRA_ARGS[@]}"
        )
        ;;
    strata)
        CMD=(
            "$BIN"
            --pack /media/timoti/Data/Strata-data/packs/swift-iq3_s
            --native "$MODEL"
            --ple-gguf /media/timoti/Data/Strata-data/models/swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf
            --expert-profile /media/timoti/Data/repos/Strata/data/expert-profile.bin
            --expert-cache auto
            --prefill auto
            --spec 4
            --spec-min-p 0.5
            --mtp "$MTP"
            --max-context 128000
            --kv int8
            --port "$PORT"
            "${EXTRA_ARGS[@]}"
        )
        ;;
esac

echo "=== Command: ${CMD[*]} ==="
echo

# ── Launch ────────────────────────────────────────────────────────────────────
ENV_PRE="$ENV_PRE" "${CMD[@]}" &
ENGINE_PID=$!
echo "Engine PID: $ENGINE_PID"

# ── Wait for health ───────────────────────────────────────────────────────────
HEALTH_URL="http://127.0.0.1:${PORT}/health"
for i in $(seq 1 120); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        echo "Engine $ENGINE_NAME is healthy on port $PORT (took ${i}s)"
        echo "ENGINE_PID=$ENGINE_PID"
        exit 0
    fi
    if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
        echo "ERROR: engine process died during startup"
        exit 1
    fi
    sleep 1
done

echo "ERROR: engine $ENGINE_NAME did not become healthy on port $PORT within 120s"
kill "$ENGINE_PID" 2>/dev/null || true
exit 1
