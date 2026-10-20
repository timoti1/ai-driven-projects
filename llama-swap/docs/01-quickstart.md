# 01. Quick start

Goal: a fresh Linux machine serving one model through llama-swap by the end
of this page. Check the [prerequisites](../README.md#prerequisites) first.

## 1. Get an engine (llama.cpp)

llama-swap does not run models itself; it supervises engine processes. The
easiest engine is the prebuilt llama.cpp binary set:

```bash
./install.sh engines --backend auto     # picks cuda/rocm/vulkan/cpu for you
```

The binary lands at a printed path like
`~/llama.cpp/llama-b11729/llama-server`. Use that path when the installer
asks for it (or pass `--llama-server`).

## 2. Get one small model

```bash
./install.sh fetch-model \
  --url https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  --dest ~/models
```

Pick any GGUF you like (Hugging Face search "GGUF"); 1-3B Q4 files need only
a couple of GB. Some repos (unsloth, Meta-based) are gated and need an HF
account + accepted license before download.

## 3. Install llama-swap

```bash
./install.sh install --template minimal \
  --llama-server ~/llama.cpp/llama-b11729/llama-server \
  --models-dir ~/models
```

Answer the prompts (listen address, paths) or add `--yes` to accept defaults.
The unit `llama-swap.service` is created, enabled and started; the installer
waits for `/health` to answer.

## 4. Talk to it

```bash
curl http://127.0.0.1:8080/v1/models
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tinyllama-1.1b-chat","messages":[{"role":"user","content":"hi"}]}'
```

The first request starts the engine (a few seconds on CPU for small models),
answers, then the model unloads after its TTL. In an OpenAI client set the
base URL to `http://<host>:8080/v1`.

## 5. Inspect and grow

```bash
./install.sh status                     # loaded vs unloaded table
./install.sh add-model --name mymodel --gguf ~/models/big.gguf \
  --backend vulkan --device Vulkan0 --ctx 8192 --macro llama-server
```

`add-model --dry-run` prints the block first. Everything is plain YAML in
`~/llama-swap/config.yml`, so you can also just edit it and run
`./install.sh validate` before restarting.

Next reads: [02 config anatomy](02-configuration-basics.md),
[03 engines](03-engines-and-backends.md),
[04 running several models](04-groups-and-routing.md).
