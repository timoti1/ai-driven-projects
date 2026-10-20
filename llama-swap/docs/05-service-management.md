# 05. Service management

## The unit

`install.sh install` renders `systemd/llama-swap.service` with your user,
install dir, config path and listen address, then enables and starts it:

```
ExecStart=<prefix>/llama-swap --config <prefix>/config.yml --listen <addr:port>
Restart=always          RestartSec=5
EnvironmentFile=-<prefix>/.llama-swap.env
```

`systemctl` commands (prefix with `sudo` unless polkit allows otherwise):

```bash
systemctl status llama-swap
sudo systemctl start|stop|restart llama-swap
sudo systemctl disable llama-swap           # stop autostart at boot
journalctl -u llama-swap -f                 # follow logs
journalctl -u llama-swap --since "1 hour ago"
```

Drop-in examples in `systemd/examples/` show real-world extras taken from
the reference host: waiting for a GPU clock-locking daemon (`lactd`) before
start, and `LimitMEMLOCK=infinity` for ROCm pinned memory. Install a drop-in
with `sudo systemctl edit llama-swap` and paste what you need.

## Config changes

```bash
sudo vim ~/llama-swap/config.yml
./install.sh validate                        # never starts, only checks
sudo systemctl restart llama-swap            # loaded models unload
```

A restart always drops currently loaded models; they come back on the next
request. Use `./install.sh configure`/`add-model` instead of hand-editing
when you want validate+restart+auto-rollback done for you.

To reload without restarting the process at all, add `--watch-config` to
`ExecStart` (upstream feature); then saving the file reloads the roster.

## Upgrading llama-swap

```bash
./install.sh upgrade                     # latest release
./install.sh upgrade --llama-swap-release v264   # pin a release
```

Order of operations: resolve release -> download with sha256 verification ->
`-validate` your config against the new binary -> stop service -> save
`llama-swap.bak-<timestamp>` -> install -> start -> `/health` loop. Any
failure restores the old binary and starts it again; your config file is
never touched by `upgrade`.

Downgrade is the same command with an older `--llama-swap-release`.

## Running without systemd

```bash
./install.sh install --no-service ...
~/llama-swap/llama-swap --config ~/llama-swap/config.yml --listen 127.0.0.1:8080 &
```

Keep it under your own supervisor (tmux, docker, runit); the installer's
`upgrade`/`configure` steps still manage files and print what to restart.
