# 04. Groups and routing: several models at once

By default llama-swap keeps exactly one model resident: requesting another
model unloads the current one. Two routers change that; pick one with
`routing.router.use`.

## The `group` router - simple and predictable

```yaml
routing:
  router:
    use: group
    settings:
      groups:
        pair:
          swap: false       # members coexist instead of replacing each other
          exclusive: true   # loading a member evicts every other group
          members: [coder-small, chat-small]
        helpers:
          swap: false
          exclusive: false  # other groups may still load alongside
          members: [embeddings, reranker]
        always-on:
          persistent: true  # nothing else may ever evict this group
          swap: false
          exclusive: false
          members: [router-model]
```

Three flags per group: `swap` (one-at-a-time inside the group),
`exclusive` (evicts other groups when a member loads), `persistent`
(never evicted by others). A model belongs to at most one group.
`configs/grouped.yaml` is a working two-model version of this.

## The `matrix` router - explicit combinations

Declare which sets of models may be resident together as boolean
expressions; the router picks the cheapest way to satisfy each request:

```yaml
routing:
  router:
    use: matrix
    settings:
      matrix:
        vars:
          giga: qwen-big          # short names keep expressions readable
          sapp: qwen-big-copy
        evict_costs:
          giga: 10                # slow-to-reload models get high cost
        sets:
          pair: "(giga) & (sapp)"
```

Rules that matter:

- `&` = run together, `|` = alternatives, `(...)` = grouping,
  `+name` = inline another set
- every subset is allowed too: set `[a, b]` also permits `[a]` alone; only
  the requested model starts (no preloading)
- a model that appears in no set can only run **alone**
- on a request the solver picks the set containing that model with the
  lowest total `evict_cost` of running models outside it

The reference host runs exactly this rule: any one of eight
Gigabyte-GPU models may coexist with any one of four Sapphire-GPU models
(`configs/example-two-gpus-production.yaml`). One big model per GPU,
twin models duplicated across GPUs for zero-downtime switching, slow custom
engines protected with `evict_costs: 10`.

## Which one to use

Start with `group`. Move to `matrix` when the allowed combinations depend
on which specific models are involved (a 70B that needs a GPU alone while
small models pair up) - groups cannot express that.

## Adding a model into a routing set

```bash
./install.sh add-model --name newmodel --gguf ~/models/new.gguf \
  --macro llama-server --matrix-var nm
```

`--matrix-var nm` also inserts `nm: newmodel` into the matrix `vars:` map so
you can reference it from set expressions. Set expressions themselves stay
hand-edited: one readable line, deliberately not generated.
