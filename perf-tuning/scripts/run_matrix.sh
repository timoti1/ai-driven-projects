#!/usr/bin/env bash
# run_matrix.sh — Matrix test runner for engine × ROCm version × parallel count.
#
# Usage:
#   run_matrix.sh [--engines ENGINE1,ENGINE2,...] [--rocms 7.8.0,7.13,7.2.4] \
#                 [--parallels 1,2] [--tag TAG]
#
# Defaults test all engines on ROCm 7.8.0 with parallel 1 and 2.
#
# Results appended to: perf-tuning/results/matrix_results.csv
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PERF_BENCH_DIR="${PROJECT_DIR}/perf-bench"
RESULTS_DIR="${PROJECT_DIR}/perf-tuning/results"
RESULTS_CSV="${RESULTS_DIR}/matrix_results.csv"

mkdir -p "$RESULTS_DIR"

# ── Defaults ──────────────────────────────────────────────────────────────────
ENGINES="${ENGINES:-avalon-hip,llama-latest-vulkan,rocmfpx-vulkan,strata}"
ROCMS="${ROCMS:-7.8.0}"
PARALLELS="${PARALLELS:-1,2}"
TAG="${TAG:-matrix-$(date +%Y%m%d-%H%M%S)}"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --engines) ENGINES="$2"; shift 2 ;;
        --rocms)   ROCMS="$2"; shift 2 ;;
        --parallels) PARALLELS="$2"; shift 2 ;;
        --tag)     TAG="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ── Init CSV ──────────────────────────────────────────────────────────────────
if [[ ! -f "$RESULTS_CSV" ]]; then
    echo "ts,tag,engine,rocm_version,hip_device,parallel,port,test,phase,depth,metric,value,first_token_s,detail" > "$RESULTS_CSV"
fi

# ── Helper: wait for engine health ────────────────────────────────────────────
wait_health() {
    local port="$1"
    local timeout="${2:-120}"
    local url="http://127.0.0.1:${port}/health"
    for i in $(seq 1 "$timeout"); do
        if curl -sf "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# ── Helper: run perf-bench and append to CSV ──────────────────────────────────
run_bench() {
    local engine="$1"
    local port="$2"
    local model="$3"
    local tag_suffix="$4"

    local full_tag="${TAG}-${engine}-${tag_suffix}"
    local out_file="${RESULTS_DIR}/run-${engine}-$(date +%Y%m%d-%H%M%S).json"

    cd "$PERF_BENCH_DIR" || exit 1
    python3 bench.py \
        --host 127.0.0.1 \
        --port "$port" \
        --model "$model" \
        --tests health,prefill,decode \
        --tag "$full_tag" \
        --repeat 2 \
        --out "$RESULTS_DIR" 2>&1 | tee -a "${RESULTS_DIR}/bench-${engine}.log"

    # Append bench.py results/runs.csv rows to master CSV with metadata
    local bench_csv="${PERF_BENCH_DIR}/results/runs.csv"
    if [[ -f "$bench_csv" ]]; then
        # Skip header, add metadata columns
        tail -n +2 "$bench_csv" | while IFS= read -r line; do
            echo "$(date -Iseconds),${full_tag},${engine},${ROCM_VERSION},${HIP_DEVICE},${PARALLEL},${port},${line}" >> "$RESULTS_CSV"
        done
        # Clear bench csv for next run
        > "$bench_csv"
    fi
}

# ── Main matrix ───────────────────────────────────────────────────────────────
IFS=',' read -ra ENGINE_LIST <<< "$ENGINES"
IFS=',' read -ra ROCM_LIST <<< "$ROCMS"
IFS=',' read -ra PARALLEL_LIST <<< "$PARALLELS"

PORTS=(5800 5801 5802 5803 5804 5805 5806 5807)
PORT_IDX=0

echo "=== Matrix Test: $TAG ==="
echo "Engines: $ENGINES"
echo "ROCm versions: $ROCMS"
echo "Parallels: $PARALLELS"
echo

for ENGINE in "${ENGINE_LIST[@]}"; do
    for ROCM_VERSION in "${ROCM_LIST[@]}"; do
        for PARALLEL in "${PARALLEL_LIST[@]}"; do
            PORT="${PORTS[$PORT_IDX]}"
            PORT_IDX=$(( (PORT_IDX + 1) % ${#PORTS[@]} ))

            echo "────────────────────────────────────────────"
            echo "Testing: engine=$ENGINE | rocm=$ROCM_VERSION | parallel=$PARALLEL | port=$PORT"
            echo "────────────────────────────────────────────"

            export ROCM_VERSION
            export HIP_DEVICE="$([[ "$ROCM_VERSION" == "7.8.0" ]] && echo "1" || echo "1")"  # default Gigabyte

            # Launch engine
            bash "$SCRIPT_DIR/launch_engine.sh" "$ENGINE" "$PORT" "$PARALLEL"
            LAUNCH_RC=$?

            if [[ $LAUNCH_RC -ne 0 ]]; then
                echo "SKIP: engine $ENGINE failed to launch (rocm=$ROCM_VERSION, parallel=$PARALLEL)"
                echo "$(date -Iseconds),${TAG}-${ENGINE}-fail,${ENGINE},${ROCM_VERSION},${HIP_DEVICE},${PARALLEL},${PORT},launch,error,0,launch_failed,0,,engine failed to start" >> "$RESULTS_CSV"
                continue
            fi

            # Wait for health
            if ! wait_health "$PORT" 120; then
                echo "SKIP: engine $ENGINE not healthy on port $PORT"
                pkill -f "port ${PORT}" 2>/dev/null || true
                continue
            fi

            # Determine model per engine
            case "$ENGINE" in
                avalon-hip)
                    MODEL="avalon-qwen3.8-flash-next-C2"
                    ;;
                llama-latest-vulkan|rocmfpx-vulkan)
                    MODEL="qwen3.8-27b-IQ3XXS"
                    ;;
                strata)
                    MODEL="qwen3.8-flash-IQ3_S"
                    ;;
                *)
                    MODEL="default"
                    ;;
            esac

            # Run benchmark
            run_bench "$ENGINE" "$PORT" "$MODEL" "rocm${ROCM_VERSION}-p${PARALLEL}"

            # Kill engine
            echo "Stopping engine on port $PORT..."
            fuser -k "${PORT}/tcp" 2>/dev/null || true
            pkill -f "llama-server.*--port ${PORT}" 2>/dev/null || true
            pkill -f "strata.*--port ${PORT}" 2>/dev/null || true
            sleep 3

            echo "Done: engine=$ENGINE | rocm=$ROCM_VERSION | parallel=$PARALLEL"
            echo
        done
    done
done

echo "=== Matrix complete ==="
echo "Results: $RESULTS_CSV"
