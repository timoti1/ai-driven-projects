# 02. Configuration basics

llama-swap's whole setup is one YAML file (default `~/llama-swap/config.yml`),
possibly split across a directory with `--config-dir`. Check any change with
`llama-swap -config FILE -validate` before restarting; the installer does this
for you automatically.

## Top-level sections

| Key | Purpose |
| --- | --- |
| `models:` | the model roster; this is the only required section |
| `macros:` | reusable strings injected into any other value |
| `routing:` | router choice (`group` or `matrix`) - see doc 04 |
| `globalTTL:` | seconds a model may idle before being unloaded |
| `unloadTimeout:` | grace period for in-flight requests during unload |
| `logLevel:` | `info` for daily use, `debug` while diagnosing |
| `healthCheckTimeout:` | seconds to wait for an engine to become ready |
| `upstream.ignorePaths:` | URL patterns proxied straight through, no model |
| `apiKeys:` | list of keys clients must present (use `${env.NAME}`) |

## Model entry fields

| Field | Meaning |
| --- | --- |
| `cmd:` | command that starts the engine; `${PORT}` is mandatory |
| `name:` | display name (the roster key is the id clients request) |
| `description:` | shown in the UI and `/v1/models` |
| `ttl:` | idle seconds before this specific model unloads |
| `env:` | extra environment variables, e.g. GPU selection |
| `capabilities:` | advertises `context`, `tools`, etc. in `/v1/models` |
| `aliases:` | extra ids that resolve to this model |
| `proxy:` | URL prefixes forwarded to this engine |
| `cmdStop:` | custom graceful shutdown command |
| `checkEndpoint:` | custom health endpoint instead of `/health` |
| `concurrencyLimit:` | max simultaneous requests per model |
| `unlisted:` | hide from `/v1/models` |
| `metadata:` | extra fields surfaced in `/v1/models` |

(`llama-swap -validate` accepts only these fields - check
`config-schema.json` from an upstream checkout for the full list.)

`cmd` is a multi-line string; newlines are whitespace, so one flag per line
(`cmd: >-`) is the house style:

```yaml
models:
  mymodel:
    cmd: >-
      ${llama-server}
      --model /models/mymodel-Q4_K_M.gguf
      --device Vulkan0
      -ngl 99
      --ctx-size 8192
      --jinja
      --host 127.0.0.1
      --port ${PORT}
```

## Macros

`macros:` keeps binaries and repeated flags in one place; refer to them as
`${name}` anywhere in the file. Names must match `[a-zA-Z0-9_-]+` and a macro
may only reference macros defined above it.

```yaml
macros:
  llama-server: /home/me/llama.cpp/llama-b11729/llama-server
  big-gpu-args: "--ngl 99 --flash-attn on --jinja"
```

## Keeping secrets out of git

Put values in `<prefix>/.llama-swap.env` (systemd `EnvironmentFile`, already
wired in the unit template) and reference them from the config:

```yaml
apiKeys:
- "${env.LLAMA_SWAP_KEY}"
```

If the variable is missing, startup fails loudly - intentional. Clients then
send `Authorization: Bearer <key>`.

## Placeholder tokens in this repo

Repo templates use `__TOKENS__` (double underscore) filled by
`install.sh configure/install` from `--llama-server`, `--models-dir`,
`--set key=value`. They never appear in a config on a deployed machine.

## Safe editing workflow

```bash
vim ~/llama-swap/config.yml
./install.sh validate                       # llama-swap -validate
sudo systemctl restart llama-swap           # or: ./install.sh configure ...
journalctl -u llama-swap -f                 # watch it come up
```

`--watch-config` (unit ExecStart flag) reloads on file changes; the installer
does not enable it by default.
