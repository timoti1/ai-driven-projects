# 03. Engines and backends

llama-swap supervises any command that serves the OpenAI API on `${PORT}`.
The default engine is llama.cpp's `llama-server`; the same pattern covers
custom engines (the reference production host runs one).

## llama.cpp: which build for which hardware

| Hardware | Build | Notes |
| --- | --- | --- |
| NVIDIA GPU | CUDA | needs working NVIDIA driver only |
| AMD GPU (RDNA2+) | Vulkan | works on stock Mesa; simplest for AMD |
| AMD GPU (ROCm/HIP) | ROCm | faster than Vulkan on many AMD cards; needs ROCm runtime; brand-new GPUs may need a source build with the right gfx target |
| Intel/AMD iGPU | Vulkan or SYCL | |
| No GPU | CPU | fine for small quantized models |

`./install.sh engines --backend auto` picks from what the machine has and
downloads the matching prebuilt tarball from llama.cpp releases
(`bin-ubuntu-<backend>-<arch>` assets). `--list-assets` shows the URLs,
`--llama-cpp-release b11729` pins an exact build.

## Picking the GPU inside llama-server

Recent llama.cpp has a unified `--device` enum: `CPU0`, `Vulkan0`,
`Vulkan1`, `CUDA0`, `HIP0`, `ROCm0`... List what exists:

```bash
llama-server --list-devices
```

Classic environment pinning still works: `HIP_VISIBLE_DEVICES=1`,
`CUDA_VISIBLE_DEVICES=0` via a model's `env:` list. `env:` entries are
per-model, which is how two models sit on two different GPUs while both
think they are device 0.

AMD example (two identical GPUs in different PCIe slots, so "Vulkan0/1"
ordering matters - see the production example config):

```yaml
    env:
    - CUDA_VISIBLE_DEVICES=
    - VK_DRIVER_FILES=/home/me/mesa-build/radeon_icd.json
    cmd: >-
      ... --device Vulkan1 ...
```

`VK_DRIVER_FILES` points at a specific Vulkan ICD - use it when you need a
newer/custom Mesa build for a brand-new AMD GPU (RDNA4 shipped before stock
distro Mesa supported it; the reference host carries its own build).

## Useful llama-server flags you will see in the examples

| Flag | Meaning |
| --- | --- |
| `-ngl 99` | offload all layers to GPU (`0` = CPU only) |
| `--ctx-size N` | context window per slot |
| `--parallel N` | concurrent requests sharing one loaded model |
| `--flash-attn on` | flash attention, keep on for GPU |
| `--jinja` | correct chat template (required for tool calls) |
| `--mmproj FILE` | vision adapter for multimodal models |
| `--spec-type draft-mtp` | MTP speculative decoding (newer llama.cpp) |
| `--cache-ram N` | KV cache offload to RAM |
| `--metrics` | per-engine `/metrics` for monitoring |

## Custom engines

Anything that binds `${PORT}` and speaks the OpenAI API works. The
production example starts a Python engine:

```yaml
  qwen3.8-flash-IQ3_S:
    cmd: >-
      /opt/engine/.venv/bin/python /opt/engine/serve/server.py
      --engine myengine
      --config /opt/engine/model.json
      --port ${PORT}
    env:
    - HIP_VISIBLE_DEVICES=1
```

Give slow-loading engines a long `healthCheckTimeout` and a high `ttl`, and
never put shell comments inside `cmd`.

Custom engines often ship their own dashboard on the same `${PORT}`.
For Strata: its web app is `/`, the Monitor dashboard is `/api-monitor`, and
request history needs `"api_monitor": true` in the engine's JSON config. The
port is whatever llama-swap assigned that load - find it with
`curl http://127.0.0.1:8080/running` (field `proxy`).

To open the dashboard from other LAN machines, set `"host": "0.0.0.0"` in
the engine's JSON (Strata's key; llama.cpp is the same via `--host 0.0.0.0`
in `cmd`). Changes apply at the engine's next load: unload the model and
let the next request reload it. Then browse
`http://<server>:<engine-port>/api-monitor`; the engine's DNS-rebinding
protection accepts requests addressed to the machine's own IPs, so a plain
LAN IP works. If you prefer keeping the engine loopback-only, tunnel instead:
`ssh -L 15807:127.0.0.1:5807 user@server`.

`./install.sh add-model --engine custom --cmd "..."` and
`--engine strata --python ... --serve-script ... --strata-config ...`
generate these blocks for you.

## vLLM, SGLang, Ollama etc.

Upstream llama-swap also ships first-class docs for vLLM, TensorRT-LLM,
LlamaEdge and SGLang - same `cmd:` pattern, see the upstream
[knowledge base](https://github.com/mostlygeek/llama-swap/tree/main/docs/kb).
Ollama deployments usually keep using Ollama's own model management.
