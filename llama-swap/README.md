# llama-swap deployment kit

Self-host your own private AI endpoint. [llama-swap](https://github.com/mostlygeek/llama-swap)
is an OpenAI-compatible proxy that keeps your GGUF/local models behind one
URL and start/stop them on demand, freeing VRAM for whichever model you
need right now. This repository gives you an installer, ready-made configs
and docs so a beginner can go from empty machine to working multi-model
setup in one evening.

- One endpoint for many models: `http://<your-server>:8080/v1/chat/completions`
- Models load on first request and unload after being idle (TTL)
- Group models so several can be resident at once (VRAM permitting)
- Engines: llama.cpp (`llama-server`) with CPU/Vulkan/CUDA/ROCm builds, or any
  custom OpenAI-compatible engine you write
- Works with any app that speaks the OpenAI API (chat UIs, IDE plugins, scripts)

## Prerequisites

Have these ready **before** running the installer:

**On the target machine (where llama-swap will run):**

- Linux x86_64 or arm64. systemd is expected for the service; `--no-service`
  covers the rest
- `bash`, `curl`, `tar`, `sha256sum` (standard on any distro), `python3` (only
  for the `add-model` command; stdlib, no pip packages)
- `sudo` rights for the user who installs (skipped with `--no-service`)
- Outbound HTTPS to `github.com` and `api.github.com` (release binaries);
  to `huggingface.co` if you download models there
- For GPU inference, pick and prepare one runtime:
  - **NVIDIA**: working NVIDIA driver (any recent CUDA-capable one)
  - **AMD**: Vulkan works out of the box on modern Mesa; ROCm/HIP needs the
    ROCm runtime; very new AMD GPUs (e.g. RDNA4) may need a recent
    Mesa/ROCm build — see [docs/03](docs/03-engines-and-backends.md)
  - **Intel/AMD iGPU**: Vulkan
  - **CPU only**: nothing extra
- Enough disk for the GGUF model files you plan to run (1–50 GB each)

**On the machine you deploy from (optional; for remote deploys):**

- `ssh` and `rsync` (SSH keys recommended; `SSH_CMD` env lets you use any
  wrapper, e.g. `sshpass`)

## Quick start

Local machine:

```bash
git clone <this-repo-url> llama-swap-deploy
cd llama-swap-deploy
./install.sh install
```

The installer asks a few questions (listen address, template, llama-server
path, models dir), downloads the latest llama-swap release (checksum
verified), writes `config.yml`, installs a systemd unit `llama-swap`, starts
it and health-checks it. Non-interactive runs: pass `--yes` plus the flags
from `./install.sh --help`.

Deploy to a remote server instead (everything else identical):

```bash
./install.sh --host timoti@192.168.10.20 install
# password auth: SSH_CMD="sshpass -p secret ssh" ./install.sh --host user@ip install
# sudo prompt on the target: SUDO_PASSWORD=... (see security note below)
```

Then get an engine and a model:

```bash
./install.sh --host timoti@192.168.10.20 engines --backend vulkan   # or cuda/cpu/rocm/auto
./install.sh --host timoti@192.168.10.20 fetch-model \
  --url https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  --dest ~/models
./install.sh --host timoti@192.168.10.20 configure --template configs/minimal.yaml \
  --llama-server ~/llama.cpp/llama-b11729/llama-server --models-dir ~/models
```

Point any OpenAI client at `http://<server>:8080/v1` and ask the proxy what
models exist: `curl http://<server>:8080/v1/models`. Models start on the
first request that names them; the web UI is at `http://<server>:8080/ui`.

## The `install.sh` command

Global options go **before** the subcommand.

| Command | What it does |
| --- | --- |
| `install` | First-time install: binary + config + systemd unit + health-check |
| `upgrade` | New llama-swap release: stop, backup binary, validate, swap, start, health-check, auto-rollback on failure |
| `configure` | Swap in a different config (template or your own file), validate, restart, rollback on failure |
| `add-model` | Append a model entry to the config from flags; `--dry-run` to preview |
| `engines` | Download a prebuilt llama.cpp engine: `--backend auto\|cpu\|vulkan\|cuda\|rocm` |
| `fetch-model` | Download a GGUF file (resumable) into the models dir |
| `status` | Binary version, service state, which models are loaded vs unloaded |
| `validate` | `llama-swap -validate` against the current config |

Useful flags: `--prefix DIR` (default `~/llama-swap`), `--listen ADDR:PORT`
(default `127.0.0.1:8080`), `--service NAME`, `--user USER`, `--no-service`,
`--no-restart`, `--llama-swap-release vNNN|latest`, `--set KEY=VAL` for any
config placeholder.

Security note: passing sudo credentials via `SUDO_PASSWORD=` leaves them in
the ssh command line. For anything beyond a home lab, use SSH keys plus a
sudoers rule allowing the needed `systemctl` commands without a password.

## Managing the service

```bash
systemctl status llama-swap
sudo systemctl restart llama-swap       # after config edits made by hand
journalctl -u llama-swap -f             # live logs
./install.sh status                     # loaded/unloaded model table
```

Which models are running right now, which are idle, how to load/unload:
[docs/06](docs/06-api-and-monitoring.md).

## Models loaded together

By default exactly one model is resident. Use the `group` router to let a
named set of models coexist, or the `matrix` router to declare exactly which
combinations may run at once (`configs/grouped.yaml` and
[docs/04](docs/04-groups-and-routing.md)). The reference host in
`configs/example-two-gpus-production.yaml` runs two GPUs with a one-model-
per-GPU pairing rule — the same pattern works for any set of GPUs.

## Documentation

| Doc | About |
| --- | --- |
| [01 Quick start](docs/01-quickstart.md) | fresh machine to first chat completion |
| [02 Configuration basics](docs/02-configuration-basics.md) | config anatomy, model fields, macros, secrets |
| [03 Engines and backends](docs/03-engines-and-backends.md) | CPU/Vulkan/CUDA/ROCm, custom engines, AMD notes |
| [04 Groups and routing](docs/04-groups-and-routing.md) | running several models at once |
| [05 Service management](docs/05-service-management.md) | systemd, logs, upgrades, rollback |
| [06 API and monitoring](docs/06-api-and-monitoring.md) | endpoints, load/unload, health, UI |
| [07 Troubleshooting](docs/07-troubleshooting.md) | common failures and what to check |
| [08 Production model catalog](docs/08-production-model-catalog.md) | what the reference host actually runs |
| [Config examples](configs/README.md) | minimal / grouped / real two-GPU production |

## Repository layout

```
install.sh                     installer + service manager (local or SSH remote)
scripts/add_model.py           config editing helper used by add-model
configs/                       example configs incl. a real production one
systemd/                       unit template + real-world drop-in examples
docs/                          the docs above
```

## License

MIT — see [LICENSE](LICENSE). llama-swap itself is upstream's project; this
repo only deploys and configures it. Model files you download are subject to
their own licenses.
