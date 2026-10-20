# Config examples

Three example llama-swap configs, from smallest to most realistic. Start
with `minimal.yaml`, graduate to `grouped.yaml` when you want models that
stay loaded together, and read `example-two-gpus-production.yaml` to see
what a real multi-GPU machine looks like.

| File | What it shows |
| --- | --- |
| `minimal.yaml` | One model, any hardware (CPU), every key explained in comments |
| `grouped.yaml` | Two models that run concurrently via the `group` router |
| `example-two-gpus-production.yaml` | Real production host: 2x AMD RX 9070, matrix router, Vulkan + ROCm + custom engine |

## Placeholder tokens

`minimal.yaml` and `grouped.yaml` contain `__TOKENS__` that `install.sh`
substitutes when it writes the config to the target machine:

| Token | Value comes from |
| --- | --- |
| `__LLAMA_SERVER__` | `--llama-server PATH` |
| `__MODELS_DIR__` | `--models-dir DIR` |
| any `__NAME__` | `--set name=value` |

If a token stays unresolved the installer aborts and lists the missing
values, unless you pass `--allow-placeholders`.

## Using a file directly

```bash
./install.sh configure --template configs/minimal.yaml \
  --llama-server /opt/llama.cpp/bin/llama-server --models-dir ~/models
```

## Adapting the production example

`example-two-gpus-production.yaml` is copied from a real host and then
cleaned up. Its paths (`/home/<user>/...`), GPU names (`Vulkan1`, `HIP1`),
library paths (`LD_LIBRARY_PATH`) and driver overrides (`VK_DRIVER_FILES`)
belong to that machine. Copy it, rename the paths to yours, and keep only
the models you actually downloaded. See docs/03 and docs/04 for what each
section means.
