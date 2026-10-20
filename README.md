# ai-driven-projects

Monorepo of self-contained projects. Each top-level folder is also available as
its own branch (same name as the folder), so a single project can be worked on in
isolation. `master` holds all folders merged together.

| Folder / branch | What it is |
|---|---|
| `llama-metrics` | Telemetry/status server for local llama.cpp + pi sessions |
| `llama-swap` | Multi-GPU llama.cpp router/swap service |
| `perf-bench` | LLM inference benchmark harness |
| `pi` | pi client + llama-metrics extension |
| `quality-bench` | Model quality benchmark suite (questions, sandboxes, scoring) |

## Layout convention

- `master` = every folder merged in.
- Branch `<name>` = only the `<name>/` folder (plus the shared root `.gitignore`
  and this README).
- To add a new project: create a branch from `master`, add the folder, commit,
  then merge back into `master`.
