# 06. API and monitoring

All endpoints verified on the current release. The proxy listens on your
`--listen` address; examples use `http://127.0.0.1:8080`. If `apiKeys:` is
configured, add `-H "Authorization: Bearer <key>"` to everything except
`/health`.

## Model traffic (what clients use)

| Endpoint | Meaning |
| --- | --- |
| `POST /v1/chat/completions` | chat; the `model` field **triggers loading** that model |
| `GET /v1/models` | every configured model with `status.value` = `loaded` or `unloaded` |
| `GET /v1/completions`, `/v1/embeddings`, `/v1/audio/...` | standard OpenAI surface (engine-dependent) |

Loading is automatic: the first request naming a model starts it (cold start
= engine boot, seconds to minutes for big models). There is no separate
"load" API - if you need warm models, keep their `ttl` high or use a
`persistent` group.

```bash
curl -s http://127.0.0.1:8080/v1/models | python3 -m json.tool | head -40
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -d '{"model":"tinyllama-1.1b-chat","messages":[{"role":"user","content":"hi"}]}'
```

## What is loaded right now

```bash
./install.sh status            # human table: loaded/unloaded + /running detail
curl -s http://127.0.0.1:8080/running          # engines live now: state, port, cmd
curl -s http://127.0.0.1:8080/v1/models | grep -o '"value":"loaded"' | wc -l
```

## Unloading

```bash
curl -X POST http://127.0.0.1:8080/api/models/unload/NAME   # one model
curl -X POST http://127.0.0.1:8080/api/models/unload        # all models
curl http://127.0.0.1:8080/unload                          # legacy unload-all
```

Models also unload themselves after `ttl` (per model) or `globalTTL` idle
seconds.

## Operations endpoints

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | liveness (`OK`) - the installer's health check |
| `GET /api/version` | llama-swap version/commit/build date |
| `GET /api/hardware` | detected GPUs/RAM as llama-swap sees them |
| `GET /logs` | engine log files listing |
| `GET /logs/stream` | live log stream of loaded engines |
| `GET /api/events` | SSE stream of model load/unload events |
| `GET /api/metrics/activity` | per-model usage/activity stats |
| `GET /api/performance` | performance sampler (`performance:` config section) |
| `GET /metrics` | Prometheus metrics |
| `GET /api/profiles` | config profile switching, if configured |
| `/ui` | browser UI: roster, live logs, load state, switch models |

## Keeping the machine happy

- `globalTTL: 1800` unloads anything idle 30 min; per-model `ttl` overrides
- `evict_costs` (matrix router) protects slow cold-start engines from being
  bounced - see doc 04
- `sendLoadingState: true` makes waiting engines report progress to clients
- `--metrics` on llama-server engines feeds per-engine Prometheus data
