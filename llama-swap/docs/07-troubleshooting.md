# 07. Troubleshooting

Work the stack top-down: config -> process -> engine -> GPU.

## Config rejected

```bash
./install.sh validate
```

Common YAML mistakes: tabs instead of spaces, a model id that already
exists, a macro referencing a later macro, a `${env.X}` whose variable is
not in `.llama-swap.env`, `${PORT}` missing from `cmd`.

## Service up but a model never loads

```bash
journalctl -u llama-swap -f        # watch what happens while you retry the request
curl -s http://127.0.0.1:8080/running
```

- `cmd:` wrong path/binary -> engine dies instantly; the log shows its stderr
- model file path wrong or on a not-yet-mounted disk
- `healthCheckTimeout:` too short for a big model -> raise it (the reference
  host uses 500 s)
- another process holds the GPU memory -> check `nvidia-smi` / `radeontop`
- out of RAM -> check `free -m`, lower `--ctx-size` or quant size

## GPU not seen or wrong GPU chosen

```bash
llama-server --list-devices
```

- Vulkan: `VK_DRIVER_FILES` pointing at a specific ICD is needed when you
  run a custom Mesa (new GPUs); with stock Mesa this var must be absent
- ROCm: `HIP_VISIBLE_DEVICES` / `LD_LIBRARY_PATH` per model env (see the
  production example); brand-new gfx targets need a source-built llama.cpp
- Two same-model GPUs swap Vulkan indices with slot order - pin devices
  explicitly and duplicate models per GPU (the "twin" pattern in the
  production config) instead of trusting one index
- ROCm pinned-memory failures: add the `LimitMEMLOCK=infinity` drop-in
  (see `systemd/examples/`)

## Models keep unloading while you still use them

Idle TTL is per model and counts *requests*, not UI sessions. Raise `ttl`,
set `globalTTL`, or put the pair in a `persistent: true` group. If two
models keep evicting each other, your router config forbids the
combination - see doc 04 and matrix `sets`.

## 404s on old endpoint names

`/api/models` was removed upstream; use `/v1/models` (or `/models`). Older
guides may also reference `/api/chat-template` - check upstream's current
routes before following blog posts.

## Remote install fails before doing anything

```bash
SSH_CMD="ssh -o StrictHostKeyChecking=no" ./install.sh --host user@ip status
```

- `rsync` missing on the target -> copy the repo there by hand and run
  `./install.sh` locally
- `sudo: a terminal is required` -> run with `-tt` style tty (drop `--yes`),
  set `SUDO_PASSWORD`, or configure passwordless sudo for `systemctl`
- GitHub blocked -> download the release tarball manually and point
  `--llama-swap-release` at a mirror, or install the binary yourself and use
  only `configure`/`add-model`

## Collect this when asking for help

Output of: `llama-swap -version`, `./install.sh status`, the failing model's
`cmd:` block (redact paths you consider private), and the `journalctl`
window around the failed load.
