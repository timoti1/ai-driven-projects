#!/usr/bin/env bash
# Deploy and manage llama-swap on a local or remote (SSH) target host.
# Usage: ./install.sh [global options] <subcommand> [subcommand options]
set -euo pipefail

LLAMA_SWAP_REPO="mostlygeek/llama-swap"
LLAMA_CPP_REPO="ggml-org/llama.cpp"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="local"
SSH_PORT=22
IDENTITY=""
REMOTE_DIR='~/.llama-swap-deploy'
YES=0

PREFIX=""
LISTEN=""
SERVICE="llama-swap"
RUNUSER="$(id -un)"
CONFIG=""
TEMPLATE=""
SWAP_RELEASE="latest"
CPP_RELEASE=""
LLAMA_SERVER=""
MODELS_DIR=""
ALLOW_PLACEHOLDERS=0
NO_SERVICE=0
NO_START=0
NO_RESTART=0
declare -a SET_KV=()
declare -a FWD=()
declare -a GLOBAL_TOKS=()
ASKPASS=""
ASKPW=""
TMP_DIRS=()

usage() {
  cat <<'EOF'
llama-swap deployment installer

Usage: ./install.sh [global options] <subcommand> [subcommand options]

Global options (BEFORE the subcommand):
  --host USER@HOST      deploy target; "local" (default) or remote over SSH
  --ssh-port N          SSH port for the remote target (default 22)
  --identity FILE       SSH private key for the remote target
  --remote-dir PATH     where repo files are staged on the target
                        (default ~/.llama-swap-deploy)
  --yes                 non-interactive mode; defaults are used silently

Subcommands:
  install               download llama-swap, write config + systemd unit,
                        start the service and health-check it
  upgrade               replace the llama-swap binary with a newer release,
                        restart the service, roll back on failure
  configure             install a new config file (template or path),
                        validate it, restart, roll back on failure
  add-model             append a model entry to the config, validate,
                        restart (python3 required)
  engines               download a prebuilt llama.cpp engine build
  fetch-model           download a GGUF model file into the models dir
  status                show service state, binary/API versions, which
                        models are loaded
  validate              run "llama-swap -validate" against a config

Common subcommand options:
  --prefix DIR          install directory (default $HOME/llama-swap, or
                        taken from the service ExecStart)
  --listen ADDR:PORT    listen address (default 127.0.0.1:8080)
  --service NAME        systemd unit name (default llama-swap)
  --user USER           service user (default current user)
  --config PATH         config path on the target (default <prefix>/config.yml)
  --no-service          skip systemd entirely
  --no-start            do not start the service
  --no-restart          do not restart after a config change
  --llama-swap-release TAG|latest   release to install/upgrade to (default latest)

install / configure options:
  --template NAME|FILE  minimal | grouped | path to a config file
  --llama-server PATH   value for the __LLAMA_SERVER__ placeholder
  --models-dir DIR      value for the __MODELS_DIR__ placeholder
  --set KEY=VALUE       extra placeholder value (repeatable; KEY is the
                        token name without the __ __ underscores)
  --allow-placeholders  keep unresolved __TOKENS__ instead of failing

add-model options (also see scripts/add_model.py --help):
  --name ID             model id (required)
  --engine llama-cpp|strata|custom
  --gguf PATH           GGUF file (llama-cpp)
  --backend cpu|vulkan|cuda|hip     default device/gpu-layers preset
  --device NAME         explicit --device value, e.g. Vulkan0, ROCm0
  --bind-host ADDR      llama-server bind address (default 127.0.0.1)
  --llama-server PATH   llama-server binary (else a "llama-server" macro
                        from the config is reused)
  --macro NAME          wrap cmd with a ${NAME} macro from the config
  --ctx N --ngl N --ttl N --parallel N --threads N
  --mmproj PATH  --flash-attn  --metrics  --context N  --description TXT
  --extra "FLAGS"       extra llama-server flags
  --env K=V             add an env var to the model entry (repeatable)
  --python PATH --serve-script PATH --strata-config JSON   (strata)
  --cmd "RAW"           raw command for the custom engine
  --matrix-var NAME     also register a matrix-router var for this model
  --dry-run             print the block instead of writing
  --list                list current model ids and exit

engines options:
  --backend auto|cpu|vulkan|cuda|rocm
  --dest DIR            extraction root (default $HOME/llama.cpp)
  --llama-cpp-release TAG   e.g. b11727 (default: newest with a match)
  --list-assets         show candidate download URLs and exit

fetch-model options:
  --url URL             GGUF download URL (required)
  --dest DIR            destination directory (required)
  --name FILE           destination file name (default from URL)

Environment:
  SUDO_PASSWORD         if set, sudo is used via askpass (less safe than
                        key auth + sudoers); prefer SSH keys
  SSH_CMD               full ssh command override, e.g.
                        SSH_CMD="sshpass -p secret ssh -o StrictHostKeyChecking=no"
EOF
}

log() { printf '[llama-swap-deploy] %s\n' "$*" >&2; }
err() { printf '[llama-swap-deploy] ERROR: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

cleanup() {
  [ -n "$ASKPASS" ] && rm -f "$ASKPASS" 2>/dev/null || true
  [ -n "$ASKPW" ] && rm -f "$ASKPW" 2>/dev/null || true
  local d; for d in "${TMP_DIRS[@]:-}"; do [ -n "$d" ] && rm -rf "$d" || true; done
}
trap cleanup EXIT

ask() { # $1 prompt, $2 default -> stdout
  local ans
  if [ -t 1 ] && [ "$YES" = 0 ] && [ -e /dev/tty ]; then
    printf '%s [%s]: ' "$1" "$2" > /dev/tty
    IFS= read -r ans < /dev/tty || ans=""
    printf '%s' "${ans:-$2}"
  else
    printf '%s' "$2"
  fi
}

ts() { date +%Y%m%d-%H%M%S; }

sudo_cmd() {
  if [ "$(id -u)" = 0 ]; then
    "$@"
  elif [ -n "${SUDO_PASSWORD:-}" ]; then
    if [ -z "$ASKPASS" ]; then
      ASKPASS="$(mktemp)"; ASKPW="$(mktemp)"
      printf '%s\n' "$SUDO_PASSWORD" > "$ASKPW"; chmod 600 "$ASKPW"
      printf '#!/bin/sh\ncat %q\n' "$ASKPW" > "$ASKPASS"; chmod 700 "$ASKPASS"
    fi
    SUDO_ASKPASS="$ASKPASS" sudo -A -p '' "$@"
  else
    sudo "$@"
  fi
}

ssh_base() {
  if [ -n "${SSH_CMD:-}" ]; then
    printf '%s' "$SSH_CMD"
  else
    local s="ssh -p $SSH_PORT"
    if [ -n "$IDENTITY" ]; then s="$s -i $IDENTITY"; fi
    printf '%s' "$s"
  fi
}

remote_exec() { # $1 = command string
  local s tt="-T"
  s="$(ssh_base)"
  if [ -t 1 ]; then tt="-tt"; fi
  # shellcheck disable=SC2086
  $s "$tt" -o StrictHostKeyChecking=accept-new "$HOST" "$1"
}

bootstrap_remote() { # rsync repo to target, run same command there
  command -v rsync >/dev/null || die "rsync is required on the deploying machine"
  log "staging repo files on $HOST:$REMOTE_DIR"
  # shellcheck disable=SC2086
  rsync -az --delete -e "$(ssh_base) -o StrictHostKeyChecking=accept-new" \
    "$REPO_DIR/" "$HOST:$REMOTE_DIR/"
  local q=()
  q+=("--host" "local")
  [ "$YES" = 1 ] && q+=("--yes")
  local tok
  for tok in "${GLOBAL_TOKS[@]:-}" "${FWD[@]:-}"; do [ -n "$tok" ] && q+=("$tok"); done
  local rq=""
  for tok in "${q[@]}"; do rq="$rq $(printf '%q' "$tok")"; done
  local envp=""
  if [ -n "${SUDO_PASSWORD:-}" ]; then
    envp="SUDO_PASSWORD=$(printf '%q' "$SUDO_PASSWORD") "
  fi
  remote_exec "cd $REMOTE_DIR && $envp./install.sh $SUBCMD$rq"
}

unit_path() { printf '/etc/systemd/system/%s.service' "$SERVICE"; }

service_installed() {
  systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE}\.service" && return 0
  [ -f "$(unit_path)" ]
}

unit_exec_start() {
  local f; f="$(unit_path)"
  [ -r "$f" ] || return 0
  grep '^ExecStart=' "$f" | tail -n1 | cut -d= -f2- || true
}

unit_opt() { # $1 = long option name without --
  local f; f="$(unit_path)"
  [ -r "$f" ] || { echo ""; return; }
  grep -oE -- "--$1([= ])[^ ]+" "$f" | tail -n1 | sed -E "s/^--$1[= ]//" || true
}

unit_work_dir() { # WorkingDirectory of the unit (abs or empty)
  local f d; f="$(unit_path)"
  [ -r "$f" ] || { echo ""; return; }
  d="$(grep -m1 '^WorkingDirectory=' "$f" | cut -d= -f2-)"
  printf '%s' "${d:-}"
}

find_binary() { # -> stdout path or empty
  local es b
  if [ -x "$PREFIX/llama-swap" ]; then printf '%s' "$PREFIX/llama-swap"; return 0; fi
  es="$(unit_exec_start || true)"; b="${es%% *}"
  if [ -n "$b" ] && [ -x "$b" ]; then printf '%s' "$b"; return 0; fi
  printf '%s' "$PREFIX/llama-swap"
}

listen_port() { # $1 listen addr -> port
  local l=${1:-8080}; printf '%s' "${l##*:}"
}

health_wait() { # $1 port
  local port=$1 i
  for i in $(seq 1 60); do
    curl -fsS -m 3 "http://127.0.0.1:${port}/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

api_get() { # $1 port, $2 path
  curl -fsS -m 5 "http://127.0.0.1:${1}${2}" 2>/dev/null || true
}

supports_flag() { # $1 binary, $2 flag name
  "$1" -h 2>&1 | grep -q -- "-$2"
}

validate_config() { # $1 binary, $2 config; non-zero exit on invalid/missing
  if [ ! -x "$1" ]; then err "no llama-swap binary at $1"; return 1; fi
  if [ ! -f "$2" ]; then err "no config at $2"; return 1; fi
  if supports_flag "$1" validate; then
    log "validating $2"
    "$1" -validate -config "$2"
  else
    log "binary lacks -validate; skipping validation"
  fi
}

resolve_swap_release() {
  if [ "$SWAP_RELEASE" != latest ]; then printf '%s' "$SWAP_RELEASE"; return; fi
  local api; api="$(mktemp)"; TMP_DIRS+=("$api")
  curl -fsS --retry 3 --max-time 30 -o "$api" \
    "https://api.github.com/repos/${LLAMA_SWAP_REPO}/releases/latest" \
    || die "cannot reach GitHub API for latest release"
  grep -m1 -oE '"tag_name":[[:space:]]*"v[0-9]+"' "$api" | grep -oE 'v[0-9]+'
}

goarch() {
  case "$(uname -m)" in
    x86_64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) die "unsupported architecture: $(uname -m)" ;;
  esac
}

fetch_swap_binary() { # $1 tag -> sets TMP_BIN
  local tag=$1 num arch tmp tgz
  num=${tag#v}; arch=$(goarch)
  tmp="$(mktemp -d)"; TMP_DIRS+=("$tmp")
  tgz="llama-swap_${num}_linux_${arch}.tar.gz"
  log "downloading llama-swap $tag (linux-$arch)"
  curl -fsSL --retry 3 --max-time 300 -o "$tmp/$tgz" \
    "https://github.com/${LLAMA_SWAP_REPO}/releases/download/${tag}/$tgz"
  log "downloaded $(du -h "$tmp/$tgz" | cut -f1)"
  local sum="$tmp/checksums.txt"
  if curl -fsSL --max-time 60 -o "$sum" \
       "https://github.com/${LLAMA_SWAP_REPO}/releases/download/${tag}/llama-swap_${num}_checksums.txt" 2>/dev/null; then
    ( cd "$tmp" && grep "linux_${arch}" checksums.txt | sha256sum -c - ) \
      || die "checksum mismatch for llama-swap $tag"
    log "checksum OK"
  else
    log "WARNING: checksums file unavailable; downloading unverified"
  fi
  tar -xzf "$tmp/$tgz" -C "$tmp"
  local bin; bin="$(find "$tmp" -type f -name llama-swap | head -n1)"
  [ -n "$bin" ] || die "llama-swap binary not found in archive"
  chmod +x "$bin"
  TMP_BIN="$bin"
}

sed_escape() { printf '%s' "$1" | sed -e 's/[&|]/\\&/g' -e 's/\\/\\\\/g'; }

resolve_template_path() {
  case "$TEMPLATE" in
    minimal) printf '%s/configs/minimal.yaml' "$REPO_DIR" ;;
    grouped) printf '%s/configs/grouped.yaml' "$REPO_DIR" ;;
    *) printf '%s' "$TEMPLATE" ;;
  esac
}

expand_tokens() { # $1 src, $2 dst
  local exprs=() kv k v left
  for kv in "${SET_KV[@]:-}"; do
    if [ -n "$kv" ]; then
      k=${kv%%=*}; v=${kv#*=}
      k=$(printf '%s' "$k" | tr '[:lower:]-' '[:upper:]_')
      exprs+=(-e "s|__${k}__|$(sed_escape "$v")|g")
    fi
  done
  if [ ${#exprs[@]} -gt 0 ]; then
    sed "${exprs[@]}" "$1" > "$2"
  else
    cp "$1" "$2"
  fi
  left=$(grep -oE '__[A-Z][A-Z0-9_]*__' "$2" | sort -u || true)
  if [ -n "$left" ] && [ "$ALLOW_PLACEHOLDERS" = 0 ]; then
    err "unresolved placeholders in $2:"
    printf '  %s\n' $left >&2
    die "supply values via --set KEY=VALUE (or --llama-server/--models-dir), or re-run with --allow-placeholders"
  fi
}

ensure_prefix() {
  [ -n "$PREFIX" ] || PREFIX="$(ask "Install directory" "$HOME/llama-swap")"
  PREFIX="${PREFIX/#\~/$HOME}"
  mkdir -p "$PREFIX"
}

detect_listen() { # fill LISTEN if empty, without prompting beyond install
  if [ -z "$LISTEN" ]; then
    local u; u="$(unit_opt listen)"
    LISTEN=${u:-127.0.0.1:8080}
  fi
}

detect_prefix_from_unit() {
  [ -n "$PREFIX" ] && return 0
  local es b
  es="$(unit_exec_start || true)"
  if [ -n "$es" ]; then
    b="${es%% *}"; PREFIX="$(dirname "$b")"
  else
    # Fallback: try to find the binary and use its directory
    local bin
    bin="$(command -v llama-swap 2>/dev/null || true)"
    if [ -n "$bin" ]; then
      PREFIX="$(dirname "$bin")"
    else
      PREFIX="$HOME/llama-swap"
    fi
  fi
  # If config not found at detected path, try common locations
  if [ ! -f "$PREFIX/config.yml" ]; then
    for try in "$HOME/llama-swap/config.yml" "/etc/llama-swap/config.yml" "/opt/llama-swap/config.yml"; do
      if [ -f "$try" ]; then
        PREFIX="$(dirname "$try")"
        break
      fi
    done
  fi
  return 0
}

target_config() {
  # --config in the unit may be relative to the unit's WorkingDirectory
  if [ -z "$CONFIG" ]; then
    local u wd
    u="$(unit_opt config)"
    if [ -z "$u" ]; then
      CONFIG="$PREFIX/config.yml"
    elif [ "${u#/}" != "$u" ]; then
      CONFIG="$u"
    else
      wd="$(unit_work_dir)"; [ -n "$wd" ] || wd="$PREFIX"
      CONFIG="$wd/$u"
    fi
  fi
}

restart_and_check() {
  detect_listen
  if service_installed && [ "$NO_RESTART" = 0 ]; then
    log "restarting service $SERVICE"
    sudo_cmd systemctl restart "$SERVICE"
    if ! health_wait "$(listen_port "$LISTEN")"; then return 1; fi
  else
    log "service not restarted (--no-restart or no systemd unit); restart manually"
  fi
}

rollback_config() { # $1 backup, $2 target, $3 binary
  err "restoring previous config"
  cp "$1" "$2"
  if service_installed; then sudo_cmd systemctl restart "$SERVICE"; fi
}

# subcommands
# (keep this file's helper functions above; usage text lives in usage())

do_install() {
  ensure_prefix
  local tag bin cfg cfgbak
  LISTEN="$(ask "Listen address" "${LISTEN:-127.0.0.1:8080}")"

  if [ -z "$TEMPLATE" ]; then
    TEMPLATE="$(ask "Config template (minimal|grouped or path)" "minimal")"
  fi
  local src; src="$(resolve_template_path)"
  [ -f "$src" ] || die "template not found: $src"

  if [ -z "$LLAMA_SERVER" ]; then
    local guess; guess="$(command -v llama-server || true)"
    LLAMA_SERVER="$(ask "llama-server binary path" "${guess:-/opt/llama.cpp/bin/llama-server}")"
  fi
  SET_KV+=("llama_server=$LLAMA_SERVER")
  if [ -z "$MODELS_DIR" ]; then
    MODELS_DIR="$(ask "Models directory (GGUF files)" "$HOME/models")"
    MODELS_DIR="${MODELS_DIR/#\~/$HOME}"
  fi
  SET_KV+=("models_dir=$MODELS_DIR")

  tag="$(resolve_swap_release)"; [ -n "$tag" ] || die "cannot resolve latest release"
  log "installing llama-swap $tag to $PREFIX"
  fetch_swap_binary "$tag"; bin="$TMP_BIN"

  cfg="$PREFIX/config.yml"
  if [ -f "$cfg" ]; then
    cfgbak="$cfg.bak-$(ts)"
    cp "$cfg" "$cfgbak"
    log "existing config kept as $cfgbak"
  fi
  expand_tokens "$src" "$cfg.new"
  mv "$cfg.new" "$cfg"
  validate_config "$bin" "$cfg" || die "invalid config: $cfg"

  cp -n "$REPO_DIR/systemd/llama-swap.env.example" "$PREFIX/.llama-swap.env.example" 2>/dev/null || true

  install -m 755 "$bin" "$PREFIX/llama-swap"
  if [ "$(id -u)" = 0 ]; then
    chown "$RUNUSER" "$PREFIX/llama-swap" "$PREFIX/config.yml"
  fi

  if [ "$NO_SERVICE" = 0 ]; then
    local unit; unit="$(mktemp)"; TMP_DIRS+=("$unit")
    sed -e "s|__USER__|$(sed_escape "$RUNUSER")|g" \
        -e "s|__INSTALL_DIR__|$(sed_escape "$PREFIX")|g" \
        -e "s|__CONFIG_PATH__|$(sed_escape "$cfg")|g" \
        -e "s|__LISTEN__|$(sed_escape "$LISTEN")|g" \
        "$REPO_DIR/systemd/llama-swap.service" > "$unit"
    log "installing systemd unit $SERVICE.service"
    sudo_cmd cp "$unit" "$(unit_path)"
    sudo_cmd systemctl daemon-reload
    sudo_cmd systemctl enable "$SERVICE"
    if [ "$NO_START" = 0 ]; then
      sudo_cmd systemctl start "$SERVICE"
      health_wait "$(listen_port "$LISTEN")" || \
        die "service did not become healthy; check: journalctl -u $SERVICE -n 50"
    fi
  else
    log "skipping systemd (--no-service); run manually:"
    log "  $PREFIX/llama-swap --config $cfg --listen $LISTEN"
  fi

  log "done. llama-swap $tag installed at $PREFIX"
  log "UI: http://${LISTEN/0.0.0.0/localhost}/ui  API base: http://${LISTEN/0.0.0.0/localhost}"
  log "models are started on first request; see docs/02-configuration-basics.md"
}

do_upgrade() {
  detect_prefix_from_unit
  local cur tag bin newver oldver
  cur="$(find_binary)"
  [ -x "$cur" ] || die "no llama-swap binary found (looked at $cur); run install first"
  oldver="$("$cur" -version 2>/dev/null | head -n1 || true)"
  target_config
  # Ensure CONFIG is set to a valid path; fall back to prefix/config.yml if needed
  if [ ! -f "$CONFIG" ]; then
    CONFIG="$PREFIX/config.yml"
  fi

  tag="$(resolve_swap_release)"; [ -n "$tag" ] || die "cannot resolve latest release"
  log "current: ${oldver:-unknown}"
  log "target:  $tag"

  fetch_swap_binary "$tag"; bin="$TMP_BIN"

  if service_installed; then
    log "stopping service $SERVICE"
    sudo_cmd systemctl stop "$SERVICE" || true
  fi

  local bak="$cur.bak-$(ts)"
  cp "$cur" "$bak"
  log "previous binary saved as $bak"
  if [ -f "$CONFIG" ]; then cp "$CONFIG" "$CONFIG.bak-$(ts)"; fi

  if ! validate_config "$bin" "$CONFIG"; then
    log "new release rejected the config; keeping previous binary"
    if service_installed; then sudo_cmd systemctl start "$SERVICE" || true; fi
    die "aborting upgrade; $bak untouched, binary unchanged"
  fi

  install -m 755 -o "$(stat -c %u "$cur")" -g "$(stat -c %g "$cur")" "$bin" "$cur"

  if service_installed && [ "$NO_START" = 0 ]; then
    detect_listen
    log "starting service $SERVICE"
    sudo_cmd systemctl start "$SERVICE"
    if ! health_wait "$(listen_port "$LISTEN")"; then
      err "new binary failed health check; rolling back"
      sudo_cmd systemctl stop "$SERVICE" || true
      cp "$bak" "$cur"; chmod 755 "$cur"
      sudo_cmd systemctl start "$SERVICE" || true
      die "rolled back to previous binary: $oldver"
    fi
  fi
  newver="$("$cur" -version 2>/dev/null | head -n1 || true)"
  log "upgraded: $oldver -> $newver"
}

do_configure() {
  detect_prefix_from_unit
  target_config
  local src bak
  if [ -z "$TEMPLATE" ]; then
    TEMPLATE="$(ask "Config template (minimal|grouped or path)" "minimal")"
  fi
  src="$(resolve_template_path)"
  [ -f "$src" ] || die "template not found: $src"
  if [ -z "$LLAMA_SERVER" ]; then
    local guess; guess="$(command -v llama-server || true)"
    LLAMA_SERVER="$(ask "llama-server binary path" "${guess:-/opt/llama.cpp/bin/llama-server}")"
  fi
  SET_KV+=("llama_server=$LLAMA_SERVER")
  if [ -z "$MODELS_DIR" ]; then
    MODELS_DIR="$(ask "Models directory (GGUF files)" "$HOME/models")"
    MODELS_DIR="${MODELS_DIR/#\~/$HOME}"
  fi
  SET_KV+=("models_dir=$MODELS_DIR")

  bak="$CONFIG.bak-$(ts)"
  if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$bak"
    log "current config saved as $bak"
  fi

  expand_tokens "$src" "$CONFIG.new"
  mv "$CONFIG.new" "$CONFIG"

  local bin; bin="$(find_binary)"
  if ! validate_config "$bin" "$CONFIG"; then
    err "new config is invalid; restoring previous one"
    [ -f "$bak" ] && cp "$bak" "$CONFIG"
    die "config was NOT applied"
  fi

  if ! restart_and_check; then
    err "service failed to come back with the new config; restoring"
    rollback_config "$bak" "$CONFIG" "$bin"
    die "rolled back to $bak"
  fi
  log "config applied: $CONFIG"
}

do_add_model() {
  detect_prefix_from_unit
  target_config
  command -v python3 >/dev/null || die "python3 is required for add-model"
  local bin; bin="$(find_binary)"
  [ -f "$CONFIG" ] || die "no config at $CONFIG"

  local dry=0 a
  for a in "$@"; do
    if [ "$a" = "--dry-run" ]; then dry=1; fi
  done
  if [ "$dry" = 1 ]; then
    python3 "$REPO_DIR/scripts/add_model.py" "$CONFIG" "$@" || die "add-model failed"
    log "dry-run: nothing written"
    return 0
  fi

  # shellcheck disable=SC2068
  python3 "$REPO_DIR/scripts/add_model.py" "$CONFIG" "$@" || die "add-model failed"

  if ! validate_config "$bin" "$CONFIG"; then
    err "config invalid after add-model; restoring backup created by add_model.py"
    restore_addmodel_backup
    die "model was NOT added"
  fi

  if ! restart_and_check; then
    err "service failed to start after add-model; restoring backup"
    restore_addmodel_backup
    restart_and_check || true
    die "rolled back"
  fi
  log "model added to $CONFIG"
}

restore_addmodel_backup() {
  local b
  b="$(ls -t "$CONFIG".bak-addmodel-* 2>/dev/null | head -n1 || true)"
  if [ -n "$b" ]; then cp "$b" "$CONFIG"; fi
}

cpp_asset_regex() { # $1 backend -> regex for a browser_download_url
  local a; a="$(goarch)"
  case "$a" in
    amd64) a=x64 ;;
    arm64) a=arm64 ;;
  esac
  case "$1" in
    cpu)    printf 'llama-b[0-9]+-bin-ubuntu-%s\.tar\.gz$' "$a" ;;
    vulkan) printf 'llama-b[0-9]+-bin-ubuntu-vulkan-%s\.tar\.gz$' "$a" ;;
    cuda)   printf 'llama-b[0-9]+-bin-ubuntu-cuda-[0-9.]+-%s\.tar\.gz$' "$a" ;;
    rocm)   printf 'llama-b[0-9]+-bin-ubuntu-rocm-[0-9.]+-%s\.tar\.gz$' "$a" ;;
    *) die "unknown backend: $1" ;;
  esac
}

auto_backend() {
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    echo cuda
  elif command -v rocminfo >/dev/null 2>&1 || lspci 2>/dev/null | grep -qi 'vga.*advanced micro devices'; then
    echo rocm
  elif command -v vulkaninfo >/dev/null 2>&1 || ls /dev/dri >/dev/null 2>&1; then
    echo vulkan
  else
    echo cpu
  fi
}

do_engines() {
  local backend="" dest="" list_assets=0
  local rest=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --backend) backend="$2"; shift 2 ;;
      --dest) dest="$2"; shift 2 ;;
      --llama-cpp-release) CPP_RELEASE="$2"; shift 2 ;;
      --list-assets) list_assets=1; shift ;;
      *) rest+=("$1"); shift ;;
    esac
  done
  if [ "${backend:-auto}" = auto ]; then backend="$(auto_backend)"; fi
  log "selected engine backend: $backend"

  local urls api
  api="$(mktemp)"; TMP_DIRS+=("$api")
  if [ -n "$CPP_RELEASE" ]; then
    curl -fsS --max-time 30 -o "$api" "https://api.github.com/repos/${LLAMA_CPP_REPO}/releases/tags/${CPP_RELEASE}"
  else
    curl -fsS --max-time 30 -o "$api" "https://api.github.com/repos/${LLAMA_CPP_REPO}/releases?per_page=5"
  fi
  urls="$(grep -oE '"browser_download_url": *"[^"]+"' "$api")"
  if [ "$list_assets" = 1 ]; then
    printf '%s\n' "$urls" | sed -E 's/.*"(https[^"]+)".*/\1/'
    return 0
  fi
  local re url
  re="$(cpp_asset_regex "$backend")"
  url="$(printf '%s\n' "$urls" | sed -E 's/.*"(https[^"]+)".*/\1/' | grep -E "$re" | head -n1 || true)"
  [ -n "$url" ] || die "no '$backend' asset found; try --list-assets and --llama-cpp-release TAG"

  dest="${dest:-$HOME/llama.cpp}"; dest="${dest/#\~/$HOME}"
  mkdir -p "$dest"
  local tmp; tmp="$(mktemp -d)"; TMP_DIRS+=("$tmp")
  log "downloading $url"
  curl -fsSL --retry 3 --max-time 600 -o "$tmp/eng.tgz" "$url"
  log "downloaded $(du -h "$tmp/eng.tgz" | cut -f1)"
  tar -xzf "$tmp/eng.tgz" -C "$dest"
  local srv
  srv="$(find "$dest" -type f -name llama-server | head -n1)"
  [ -n "$srv" ] || die "llama-server binary not found after extraction under $dest"
  chmod +x "$srv"
  log "engine ready: $srv"
  log "use it in configs, e.g.: ./install.sh configure --llama-server $srv ..."
}

do_fetch_model() {
  local url="" dest="" name=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --url) url="$2"; shift 2 ;;
      --dest) dest="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      *) die "unknown fetch-model option: $1" ;;
    esac
  done
  [ -n "$url" ] || die "fetch-model requires --url"
  [ -n "$dest" ] || die "fetch-model requires --dest"
  dest="${dest/#\~/$HOME}"
  name=${name:-$(basename "${url%%\?*}")}
  mkdir -p "$dest"
  log "downloading $name into $dest"
  curl -fsSL -C - --retry 3 --max-time 7200 -o "$dest/$name" "$url"
  log "saved: $dest/$name ($(du -h "$dest/$name" | cut -f1))"
}

do_status() {
  detect_prefix_from_unit
  detect_listen
  local bin port; bin="$(find_binary)"; port="$(listen_port "$LISTEN")"
  echo "== binary =="
  if [ -x "$bin" ]; then "$bin" -version 2>/dev/null | head -n1 || true; else echo "not found at $bin"; fi
  echo
  echo "== service =="
  if service_installed; then
    echo "unit: $SERVICE ($(systemctl is-active "$SERVICE" 2>/dev/null || true)) enabled=$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
    echo "exec: $(unit_exec_start)"
  else
    echo "no systemd unit named $SERVICE"
  fi
  echo
  echo "== api (http://127.0.0.1:$port) =="
  echo -n "version:  "; api_get "$port" /api/version; echo
  echo -n "health:   "; curl -fsS -o /dev/null -w '%{http_code}\n' --max-time 5 "http://127.0.0.1:$port/health" 2>/dev/null || echo "unreachable"
  local models loaded unloaded
  models="$(api_get "$port" /v1/models)"
  if [ -n "$models" ]; then
    loaded=$(printf '%s' "$models" | grep -o '"value":"loaded"' | wc -l || true)
    unloaded=$(printf '%s' "$models" | grep -o '"value":"unloaded"' | wc -l || true)
    echo "models:   $loaded loaded, $unloaded unloaded"
    if command -v python3 >/dev/null; then
      printf '%s' "$models" | python3 -c 'import json,sys
d=json.load(sys.stdin)
for m in d.get("data",[]):
    print("  {id:<40} {st}".format(id=m["id"], st=m.get("status",{}).get("value","?")))' 2>/dev/null || true
    fi
  fi
  local running
  running="$(api_get "$port" /running)"
  if [ -n "$running" ] && command -v python3 >/dev/null; then
    echo "running:"
    printf '%s' "$running" | python3 -c 'import json,sys
d=json.load(sys.stdin)
for r in d.get("running",[]):
    print("  {m:<40} state={s} proxy={p}".format(m=r.get("model","?"), s=r.get("state","?"), p=r.get("proxy","?")))' 2>/dev/null || true
  fi
}

do_validate() {
  detect_prefix_from_unit
  target_config
  [ -f "$CONFIG" ] || { CONFIG="$PREFIX/config.yml"; }  # unit-relative path sanity
  validate_config "$(find_binary)" "$CONFIG" || die "validation failed"
}

# arg parsing: global options before the subcommand, subcommand options after

SUBCMD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --ssh-port) SSH_PORT="$2"; shift 2 ;;
    --identity) IDENTITY="$2"; shift 2 ;;
    --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
    --yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do FWD+=("$1"); shift; done ;;
    -*) FWD+=("$1"); shift ;;
    *)
      SUBCMD="$1"; shift
      while [ $# -gt 0 ]; do
        case "$1" in
          --host) HOST="$2"; shift 2 ;;
          --ssh-port) SSH_PORT="$2"; shift 2 ;;
          --identity) IDENTITY="$2"; shift 2 ;;
          --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
          --yes) YES=1; shift ;;
          --prefix) PREFIX="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --listen) LISTEN="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --service) SERVICE="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --user) RUNUSER="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --config) CONFIG="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --template) TEMPLATE="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --llama-swap-release) SWAP_RELEASE="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --llama-server) LLAMA_SERVER="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --models-dir) MODELS_DIR="$2"; GLOBAL_TOKS+=("$1" "$2"); shift 2 ;;
          --allow-placeholders) ALLOW_PLACEHOLDERS=1; GLOBAL_TOKS+=("$1"); shift ;;
          --no-service) NO_SERVICE=1; GLOBAL_TOKS+=("$1"); shift ;;
          --no-start) NO_START=1; GLOBAL_TOKS+=("$1"); shift ;;
          --no-restart) NO_RESTART=1; GLOBAL_TOKS+=("$1"); shift ;;
          *) FWD+=("$1"); shift ;;
        esac
      done
      break ;;
  esac
done

[ -n "$SUBCMD" ] || { usage; exit 1; }

if [ "$HOST" != local ] && [ "$HOST" != localhost ]; then
  bootstrap_remote
  exit $?
fi

case "$SUBCMD" in
  install)   do_install ;;
  upgrade)   do_upgrade ;;
  configure) do_configure ;;
  add-model) do_add_model "${FWD[@]+"${FWD[@]}"}" ;;
  engines)   do_engines "${FWD[@]+"${FWD[@]}"}" ;;
  fetch-model) do_fetch_model "${FWD[@]+"${FWD[@]}"}" ;;
  status)    do_status ;;
  validate)  do_validate ;;
  *) die "unknown subcommand: $SUBCMD (see --help)" ;;
esac
