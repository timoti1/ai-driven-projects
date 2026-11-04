#!/usr/bin/env bash
# vk_mem_probe.sh — capture where a ggml-vulkan allocation actually lands, and which
# fused ops survived startup. This is log capture, not a benchmark: it answers
# "is the model resident, did flash attention stay on, where is the KV cache"
# without needing a quiet card or a timed run.
#
# Required env:
#   BIN      path to a llama-server built with the Vulkan backend
#   MODEL    path to the GGUF file
# Optional env:
#   MMPROJ     vision projector GGUF
#   DEVICE     backend device name (default: Vulkan0)
#   CTX        context size; leave unset to let --fit decide
#   KV_TYPE    -ctk/-ctv type (default: q4_0)
#   PARALLEL   --parallel value (default: 1)
#   PORT       listen port (default: 5897)
#   THREADS    --threads (default: 8)
#   EXTRA      extra server args, one shell word per entry, e.g.
#              EXTRA="--flash-attn on --spec-type draft-mtp --spec-draft-n-max 3"
#   VK_ENV     extra "NAME=value" pairs for the process environment
#   LOG        where to write the server log (default: ./vk_probe_<PORT>.log)
#   WAIT       seconds to wait for load (default: 900)
#
# Finding the residency ceiling (no separate script needed): run this with CTX unset
# to let the fitter choose, then re-run with explicit CTX values and watch for the
# first run that fails to allocate. The last success is the ceiling.
#
# Exit codes: 0 = probe completed, 2 = load failed, 1 = usage error.

set -uo pipefail

: "${BIN:?set BIN to the llama-server path}"
: "${MODEL:?set MODEL to the GGUF path}"
DEVICE="${DEVICE:-Vulkan0}"
KV_TYPE="${KV_TYPE:-q4_0}"
PARALLEL="${PARALLEL:-1}"
PORT="${PORT:-5897}"
THREADS="${THREADS:-8}"
WAIT="${WAIT:-900}"
LOG="${LOG:-./vk_probe_${PORT}.log}"
BASE="http://127.0.0.1:${PORT}"

[ -x "$BIN" ] || { echo "BIN not executable: $BIN" >&2; exit 1; }
[ -f "$MODEL" ] || { echo "MODEL not found: $MODEL" >&2; exit 1; }

args=(--model "$MODEL" --device "$DEVICE" -ngl 99 -lv 5 --no-log-timestamps
      --flash-attn on --parallel "$PARALLEL"
      --batch-size 2048 --ubatch-size 1024 --threads "$THREADS"
      -ctk "$KV_TYPE" -ctv "$KV_TYPE" --cache-ram 0
      --host 127.0.0.1 --port "$PORT")
[ -n "${CTX:-}" ] && args+=(--ctx-size "$CTX")
[ -n "${MMPROJ:-}" ] && args+=(--mmproj "$MMPROJ")
# shellcheck disable=SC2206
[ -n "${EXTRA:-}" ] && args+=($EXTRA)

runenv=(env -u CUDA_VISIBLE_DEVICES)
for kv in ${VK_ENV:-}; do runenv+=("$kv"); done
"${runenv[@]}" "$BIN" "${args[@]}" >"$LOG" 2>&1 &
pid=$!

rc=0
for _ in $(seq 1 "$WAIT"); do
  if ! kill -0 "$pid" 2>/dev/null; then rc=2; break; fi
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 1
done
[ "$rc" = 0 ] && [ "${code:-}" != "200" ] && rc=2

# One short request so that per-op placement for a real decode pass is exercised.
[ "$rc" = 0 ] && curl -s -m 120 "$BASE/v1/chat/completions" -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"name three minerals"}],"max_tokens":48}' >/dev/null 2>&1

kill -TERM "$pid" 2>/dev/null; sleep 3; kill -KILL "$pid" 2>/dev/null
wait "$pid" 2>/dev/null

report() { grep -aiE "$1" "$LOG" 2>/dev/null | head -n "${2:-12}"; }

echo "================= vk_mem_probe report ================="
echo "device : $DEVICE   ctx: ${CTX:-<fit>}   kv: $KV_TYPE   parallel: $PARALLEL"
echo "log    : $LOG"
echo
echo "--- device / feature lines ---"
report 'matrix cores|cooperative|coopmat|host_visible|Vulkan[0-9]:' 8
echo
echo "--- offload depth ---"
report 'offloaded|load time|model buffer size' 8
echo
echo "--- cache allocation (this is the residency evidence) ---"
report 'KV buffer size|RS buffer size|kv.*size|recurrent' 10
echo
echo "--- compute buffers ---"
report 'compute buffer' 12
echo
echo "--- fused ops: enabled or silently disabled? ---"
report 'resolve_fused_ops|Flash Attention|gated delta|fgdn|indexer|not supported, set to disabled' 12
echo
echo "--- spill / capacity signals ---"
report 'failed to allocate|out of memory|does not fit|fallback|system memory|assigned to device CPU|no sufficiently large' 12
echo
echo "--- verdict ---"
if [ "$rc" = 2 ]; then
  echo "LOAD FAILED — this is a harness fault, not a measurement. Tail of log:"
  tail -n 12 "$LOG"
  exit 2
fi
if report 'assigned to device CPU|fallback|system memory|no sufficiently large' 1 | grep -q .; then
  echo "NON-RESIDENT signals present — see 'spill / capacity signals' above."
else
  echo "No spill signals in this log. Confirm against the buffer sizes above:"
  echo "  weights + KV + RS + compute buffers must sum below the device's reported"
  echo "  free memory, or the run is resident only by luck."
fi
if report 'not supported, set to disabled' 1 | grep -qi 'flash'; then
  echo "FLASH ATTENTION WAS DISABLED — timings from this run are not comparable"
  echo "with a run where FA stayed on."
fi
if ! report 'offloaded' 1 | grep -q .; then
  echo "NOTE: no 'offloaded' line found; verbosity may differ in this build. Read"
  echo "the log directly rather than trusting this verdict."
fi
