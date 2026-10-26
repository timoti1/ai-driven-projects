#!/usr/bin/env bash
# Per-category benchmark runner: one fresh Docker container per bench (10 launches).
# Each launch mounts only its own questions (+ clean task sandboxes) and the shared
# results dir; every pi session starts with a clean context, so no compaction mid-run.
set -euo pipefail

MODEL="${1:?Usage: ./run.sh MODEL [RUN_ID] [NOTE] [SEED]}"   # bare model id or provider/id form; endpoint from env vars below (default: LM Studio)
# OpenRouter example: BENCH_HOST=openrouter.ai BENCH_PORT=443 BENCH_SCHEME=https BENCH_PATH_PREFIX=/api BENCH_API_KEY_ENV=OPENROUTER_API_KEY BENCH_API=openai-completions ./run.sh nvidia/nemotron-3.5-super-vl:free
RUN_ID="${2:-$(date +%Y%m%d-%H%M%S)}"                 # timestamp by default so parallel campaigns never collide
NOTE="${3:-}"                                          # free text -> meta_<RUN_NAME>.json (Note column of compare/report)
SEED="${4-${BENCH_SEED:-1234}}"                       # generation seed -> samplingParams.seed (needs a server that honors seed); default 1234, pass "" to disable
if [[ -n "$SEED" && ! "$SEED" =~ ^[0-9]+$ ]]; then echo "!! seed must be an integer, got: $SEED" >&2; exit 1; fi

BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="bench-sandbox"
SAFE_MODEL="${MODEL//\//-}"; SAFE_MODEL="${SAFE_MODEL//:/-}"  # dir/file-safe form (slashes and colons -> dashes)
RUN_NAME="${SAFE_MODEL}_${RUN_ID}"                     # one run = runs/<RUN_NAME>/ + .stage/<RUN_NAME>/
STAGE="$BENCH_DIR/.stage/$RUN_NAME"                    # per-launch stage (question/task copies); deleted on full success
RUNDIR="$BENCH_DIR/runs/$RUN_NAME"                     # persistent results; mounted as /work in every launch

# Inference endpoint. Override via env vars (LMSTUDIO_* kept as aliases):
BENCH_HOST="${BENCH_HOST:-${BENCH_LMSTUDIO_HOST:-192.168.1.104}}"      # inference server host
BENCH_PORT="${BENCH_PORT:-${BENCH_LMSTUDIO_PORT:-8080}}"              # inference server port
BENCH_SCHEME="${BENCH_SCHEME:-http}"                                # http or https
BENCH_PATH_PREFIX="${BENCH_PATH_PREFIX:-}"                          # URL prefix before /v1/... (e.g. /api for OpenRouter)
CTX="${BENCH_CTX:-}"                                                # contextWindow for models.json; empty = auto from server context_length
BENCH_API_KEY_ENV="${BENCH_API_KEY_ENV:-}"                          # env var name holding the API key (e.g. OPENROUTER_API_KEY)
BENCH_API_KEY="${BENCH_API_KEY:-${BENCH_LMSTUDIO_KEY:-lmstudio}}"     # API key literal fallback (prefer BENCH_API_KEY_ENV)
BENCH_API="${BENCH_API:-openai-completions}"                        # pi agent 'api' value: openai-completions | openai-chat

# resolve API key: env var named by BENCH_API_KEY_ENV > BENCH_API_KEY literal
KEY="$BENCH_API_KEY"
if [[ -n "$BENCH_API_KEY_ENV" ]]; then
    env_val="${!BENCH_API_KEY_ENV}"
    if [[ -n "$env_val" ]]; then KEY="$env_val"; fi
fi

# Provider id used in pi's models.json. Auto-detected from host when BENCH_PROVIDER
# is not set: openrouter.ai -> "openrouter" (pi finds OPENROUTER_API_KEY in auth.json),
# anything else -> "openai" (OpenAI-compatible endpoint via models.json baseUrl + apiKey).
# Override with BENCH_PROVIDER if you need a different provider label.
if [[ -z "${BENCH_PROVIDER:-}" && "$BENCH_HOST" == *"openrouter"* ]]; then
    PROV="openrouter"
else
    PROV="${BENCH_PROVIDER:-openai}"
fi
MID="$MODEL"
# Full model id stays as given (e.g. "nvidia/nemotron-3.5-lightning:free" for OpenRouter).
# Bare name keeps PROV as auto-detected; no provider splitting is done automatically.

ORDER=(mmlu gsm8k arc hellaswag math winogrande bbh humaneval terminal terminal_hard)  # INSTRUCTIONS.md order, one container per entry

# --- preflight --------------------------------------------------------------------------
BASE_URL="${BENCH_SCHEME}://${BENCH_HOST}:${BENCH_PORT}${BENCH_PATH_PREFIX}/v1"
MODELS_URL="${BASE_URL}/models"
MODELS_JSON=$(curl -fsS --max-time 5 -H "Authorization: Bearer $KEY" "$MODELS_URL") || {
    echo "!! cannot reach inference server at $MODELS_URL (set BENCH_HOST/PORT/SCHEME/PATH_PREFIX if different)" >&2
    exit 1
}
# exact model id must exist on the server, or every container dies with a 404
# (feed JSON via stdin to avoid argument-list-too-long on huge model catalogs like OpenRouter)
if ! printf '%s' "$MODELS_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if any(m.get("id")==sys.argv[1] for m in data["data"]) else 1)' "$MID"; then
    echo "!! model '$MID' not found on $BENCH_HOST:$BENCH_PORT. Available:" >&2
    printf '%s' "$MODELS_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); [print("   ", m["id"]) for m in sorted(data["data"], key=lambda m: m["id"])]' >&2
    exit 1
fi
# auto-derive the real engine context window (llama-swap reports context_length per model;
# a too-large CTX causes overflow-compactions mid-session which corrupt batch bookkeeping)
if [[ -z "$CTX" ]]; then
    CTX="$(printf '%s' "$MODELS_JSON" | python3 -c 'import json,sys
ms=[m for m in json.load(sys.stdin)["data"] if m.get("id")==sys.argv[1]]
print(ms[0].get("context_length") or ms[0].get("context_window") or "")' "$MID")"
    if [[ -z "$CTX" ]]; then
        echo "!! server does not report context_length for '$MID'; set BENCH_CTX=<ctx size> explicitly (or pass BENCH_CTX=8192 etc)" >&2
        CTX=""
    else
        echo "=== context window: CTX=$CTX auto-detected from server for $MID (override with BENCH_CTX) ===" >&2
    fi
fi

# resolve the GGUF file this model id actually loads: server config.yml is the only
# place with paths (/v1/models hides them; engine-wrapper models resolve via their engine JSON).
MODEL_FILE=""
# GGUF lookup only applies to local llama-swap endpoints; skip for remote (OpenRouter etc.)
if [[ "${BENCH_SKIP_FILE_LOOKUP:-0}" != "1" ]] && command -v sshpass >/dev/null \
    && [[ "$BENCH_SCHEME" == "http" && -z "$BENCH_PATH_PREFIX" ]]; then
    SSH_TARGET="${BENCH_SSH_TARGET:-timoti@$BENCH_HOST}"
    SSH_PASS="${BENCH_SSH_PASS:-enter1}"
    CFG_RMT="${BENCH_SWAP_CONFIG:-\$HOME/llama-swap/config.yml}"
    MODEL_FILE="$(sshpass -p "$SSH_PASS" ssh -T -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
        "$SSH_TARGET" "python3 - '$MID' \"$CFG_RMT\"" < "$BENCH_DIR/bin/_model_file.py" 2>/dev/null | tr -d '\r' | tail -n1 || true)"
fi
if [[ -n "$MODEL_FILE" ]]; then
    echo "=== model file: $MODEL_FILE (auto-resolved from llama-swap config) ===" >&2
else
    echo "!! model file not auto-resolved (no sshpass / unreachable ssh; set BENCH_SSH_TARGET/BENCH_SSH_PASS or BENCH_SKIP_FILE_LOOKUP=1); reports fall back to model_files.json" >&2
fi

# --- per-run scaffolding ------------------------------------------------------------------
mkdir -p "$RUNDIR"
PIHOME="$STAGE/pi"; mkdir -p "$PIHOME/agent"
# pin generation RNG when a seed was given (pi passes samplingParams through to the OpenAI-compat request)
SAMPLING=""
CTX_JSON=""
if [[ -n "$CTX" ]]; then
    CTX_JSON=", \"contextWindow\": $CTX"
fi
if [[ -n "$SEED" ]]; then
    SAMPLING=", \"samplingParams\": { \"seed\": $SEED }"
    echo "=== generation seed: $SEED (reproducible sampling; engine must honor 'seed')" >&2
fi
cat > "$PIHOME/agent/models.json" <<EOF
{ "providers": { "$PROV": {
    "baseUrl": "$BASE_URL",
    "api": "$BENCH_API",
    "apiKey": "$KEY",
    "models": [ { "id": "$MID"$CTX_JSON$SAMPLING } ]
} } }
EOF
# write auth.json so pi finds the provider key inside the container
if [[ -n "${BENCH_API_KEY_ENV:-}" ]]; then
    auth_val="${!BENCH_API_KEY_ENV}"
    if [[ -n "$auth_val" ]]; then
        python3 - "$PIHOME/agent/auth.json" "$PROV" "$auth_val" <<'PYEOF'
import json, os, sys
path, prov, key = sys.argv[1], sys.argv[2], sys.argv[3]
d = {}
if os.path.exists(path):
    try:
        d = json.load(open(path))
    except Exception:
        d = {}
d[prov] = {"type": "api_key", "key": key}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(d, f, indent=2)
PYEOF
    fi
fi

# run metadata: notes (if given) + the context window this run actually used
mkdir -p "$BENCH_DIR/meta"
if [[ -n "$NOTE" ]]; then
    python3 "$BENCH_DIR/bin/_meta.py" "$BENCH_DIR/meta/meta_$RUN_NAME.json" "notes=$NOTE" "context_size=$CTX"
else
    python3 "$BENCH_DIR/bin/_meta.py" "$BENCH_DIR/meta/meta_$RUN_NAME.json" "context_size=$CTX"
fi
if [[ -n "$SEED" ]]; then python3 "$BENCH_DIR/bin/_meta.py" "$BENCH_DIR/meta/meta_$RUN_NAME.json" "seed=$SEED"; fi
if [[ -n "$MODEL_FILE" ]]; then python3 "$BENCH_DIR/bin/_meta.py" "$BENCH_DIR/meta/meta_$RUN_NAME.json" "model_file=$MODEL_FILE"; fi

# --- helpers ------------------------------------------------------------------------------
qcount() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$BENCH_DIR/questions/questions_$1.json"; }

done_count() {  # $1=bench -> answers already recorded in RUNDIR for this bench (0 if none)
    python3 - "$RUN_NAME" "$1" <<'EOF'
import glob, json, os, sys
run_name, b = sys.argv[1], sys.argv[2]
rd = f"runs/{run_name}"
if b in ("mmlu", "gsm8k", "arc", "hellaswag", "math", "winogrande", "bbh"):
    try: print(len(json.load(open(f"{rd}/answers.json")).get(b, {})))
    except Exception: print(0)
elif b == "humaneval":
    p = f"{rd}/solutions.py"
    print(sum(l.startswith("def ") for l in open(p)) if os.path.exists(p) else 0)
else:  # terminal / terminal_hard -> collected <sandbox>.txt files
    print(len(glob.glob(f"{rd}/{b}/*.txt")))
EOF
}

# $1=bench, $2=prompt -> one fresh container; _progress.py streams progress and kills on loop/idle.
run_bench() {
    local b="$1" prompt="$2" cname="bench-$RUN_NAME-$b" tasks=""
    [[ "$b" == terminal || "$b" == terminal_hard ]] && tasks="-v $STAGE/$b/tasks:/tasks"
    docker rm -f "$cname" >/dev/null 2>&1 || true
    # prompt goes via env (not argv) so quotes/newlines in it are safe; pi runs with a fresh session (--no-session).
    local script="cd /bench && exec pi --no-session --mode json --provider '$PROV' --model '$MID' \"\$BENCH_PROMPT\""
    docker run --rm \
        -e "BENCH_PROMPT=$prompt" \
        --name "$cname" \
        --add-host host.docker.internal:host-gateway \
        -v "$STAGE/$b/questions:/questions:ro" \
        -v "$RUNDIR:/work" \
        $tasks \
        -v "$BENCH_DIR/INSTRUCTIONS.md:/bench/INSTRUCTIONS.md:ro" \
        -v "$PIHOME:/root/.pi" \
        --entrypoint /bin/bash \
        "$IMAGE" -c "$script" \
        |
        # raw event log per bench, kept for debugging and compaction audits
        tee -a "$RUNDIR/pi_stream_$b.jsonl" \
        | python3 "$BENCH_DIR/bin/_progress.py" --name "$cname" --run-name "$RUN_NAME" --bench "$b" || return 1
}

# terminal benches only: copy out.txt from each task sandbox into runs/<RUN_NAME>/<bench>/ (score.py reads these).
collect_terminal() {
    local b="$1" root="terminal_sandboxes${b#terminal}"
    python3 - "$STAGE/$b/tasks/$root" "$BENCH_DIR/questions/questions_$b.json" "$RUNDIR/$b" <<'EOF'
import json, os, shutil, sys
tasks_root, qfile, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out_dir, exist_ok=True)
n = 0
for q in json.load(open(qfile)):
    src = os.path.join(tasks_root, q["sandbox"], "out.txt")
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(out_dir, f"{q['sandbox']}.txt")); n += 1
print(f"collected {n} terminal outputs -> runs/.../{os.path.basename(out_dir)}/", file=sys.stderr)
EOF
}

# --- main loop: one container per bench ----------------------------------------------------
FAILED=()
i=0
for b in "${ORDER[@]}"; do
    i=$((i + 1))
    N="$(qcount "$b")"

    # fresh stage for this category: only its questions (+ clean task sandboxes) exist inside.
    mkdir -p "$STAGE/$b/questions"
    cp "$BENCH_DIR/questions/questions_$b.json" "$STAGE/$b/questions/"
    if [[ $b == terminal || $b == terminal_hard ]]; then   # terminal benches need writable task dirs, not just questions
        rm -rf "$STAGE/$b/tasks"
        mkdir -p "$STAGE/$b/tasks/terminal_sandboxes${b#terminal}"
        cp -r "$BENCH_DIR/terminal_sandboxes${b#terminal}/." "$STAGE/$b/tasks/terminal_sandboxes${b#terminal}/"
        find "$STAGE/$b/tasks" -name 'out*' -delete   # wipe any leftover outputs of other models
        # resume: restore this run's already-solved task outputs into the stage
        for f in "$RUNDIR/$b"/*.txt; do
            [ -f "$f" ] || continue
            t="$(basename "$f" .txt)"
            d="$STAGE/$b/tasks/terminal_sandboxes${b#terminal}/$t"
            [ -d "$d" ] && cp "$f" "$d/out.txt"
        done
        ls "$STAGE/$b/tasks"/*/*/out.txt >/dev/null 2>&1 && echo "   (restored $(ls "$STAGE/$b/tasks"/*/*/out.txt | wc -l) solved tasks into stage)" >&2 || true
    fi

    if [[ "${RESUME:-0}" == "1" ]] && [ "$(done_count "$b")" = "$N" ]; then
        echo "=== [$i/10] $b already complete ($N/$N) — skipped (RESUME)" >&2
        continue
    fi

    # per-bench prompt: the model sees only this one category.
    common="Read /bench/INSTRUCTIONS.md first and follow it exactly, but do ONLY the '$b' benchmark now — this container holds that single category; every other benchmark is a separate session you must not touch (their questions do not even exist in this container). Start with python3 /bench/_todo.py $b : answers already recorded from a previous attempt are LOCKED — never re-answer or overwrite them; _show_batch.py already hides them. Your job is only the remaining questions. Record your start time with: date +%s"
    case "$b" in
        mmlu|gsm8k|arc|hellaswag|math|winogrande|bbh)
            prompt="$common Work the remaining questions of '$b' via _show_batch.py batches of 10 (it shows only unanswered ones), recording each answer once with _append_batch.py. Before finishing run _todo.py $b — it must report remaining 0 — then run: _time.py $b <start_epoch>"
            ;;
        humaneval)
            prompt="$common Functions already defined in /work/solutions.py are LOCKED — never rewrite them; _show_batch.py hides their prompts. Write the MISSING functions into /work/solutions.py following the HumanEval section of INSTRUCTIONS.md (full function bodies, imports inside the body, no Tuple/Any/Dict in signatures). Before finishing run _todo.py humaneval — it must report remaining 0. Then run: _time.py humaneval <start_epoch>"
            ;;
        *)  # terminal | terminal_hard
            prompt="$common For each of the $N tasks listed in /questions/questions_$b.json: a sandbox that ALREADY contains out.txt is DONE — skip it completely and never redo it; only work tasks whose sandbox has no out.txt. Work only inside your task's sandbox dir under /tasks/terminal_sandboxes${b#terminal}/, read task.md first, inspect data with head -1 before scripting (never hard-code field numbers), and write the final answer as one line to out.txt IN THAT SAME DIR. Before finishing verify every task dir has out.txt (find /tasks -name out.txt | wc -l must be $N); then run: _time.py $b <start_epoch>"
            ;;
    esac

    echo "" >&2
    echo "=== [$i/10] bench=$b ($N questions) — fresh container, clean context ===" >&2
    # keep the log of a previous attempt of this bench (retries must not truncate it)
    [ -f "$RUNDIR/pi_stream_$b.jsonl" ] && mv "$RUNDIR/pi_stream_$b.jsonl" "$RUNDIR/pi_stream_$b.attempt$(( $(ls "$RUNDIR"/pi_stream_$b.attempt*.jsonl 2>/dev/null | wc -l) + 1 )).jsonl"
    if run_bench "$b" "$prompt"; then :; else FAILED+=("$b"); fi
    [[ $b == terminal || $b == terminal_hard ]] && collect_terminal "$b"   # salvage even partial terminal work

done

# --- summary -------------------------------------------------------------------------------
echo "=== run $RUN_NAME finished ===" >&2
# auto-count context compactions from this run's event logs (all attempts)
COMPACT=$(cat "$RUNDIR"/pi_stream_*.jsonl 2>/dev/null | grep -cE '"type":"compaction_start"')
python3 "$BENCH_DIR/bin/_meta.py" "$BENCH_DIR/meta/meta_$RUN_NAME.json" "compactions=$COMPACT"
MISSING=()
for b in "${ORDER[@]}"; do
    d="$(done_count "$b")"; t="$(qcount "$b")"
    [[ "$d" -lt "$t" ]] && MISSING+=("$b ($d/$t)")
done
if [ ${#FAILED[@]} -gt 0 ]; then echo "!! failed benches: ${FAILED[*]}" >&2; fi
if [ ${#MISSING[@]} -eq 0 ]; then
    rm -rf "$STAGE"   # success -> stage no longer needed (results live in runs/<RUN_NAME>/)
    echo "ALL COMPLETE — results in $RUNDIR. Score with: ./.benchenv/bin/python score.py $RUN_NAME" >&2
else
    echo "!! incomplete benches: ${MISSING[*]}" >&2
    echo "   stage kept at $STAGE (partial terminal outputs are salvageable from here)" >&2
    echo "   redo only the missing ones with: RESUME=1 ./run.sh $MODEL <RUN_ID>" >&2
fi
