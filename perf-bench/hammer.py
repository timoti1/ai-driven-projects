#!/usr/bin/env python3
"""hammer.py - saturate an OpenAI-compatible endpoint to create real background load.

Used by `ab.py probe` as the interfering workload: contention claims are only
worth anything if the competing engine is genuinely busy, and driving it from
the server side keeps the measuring machine out of the result.

  python hammer.py --host 127.0.0.1 --port 8080 --model some-model --concurrency 2
  python hammer.py --host ROUTER --port 8080 --model M --duration 300 --max-tokens 512
"""
import argparse
import json
import threading
import time
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--model", required=True)
    p.add_argument("--path-prefix", default="")
    p.add_argument("--prompt", default="Write a long, detailed essay about distributed systems, "
                                       "cache coherence, and the failure modes of replicated logs.")
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--duration", type=int, default=120, help="seconds to keep hammering")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--temperature", type=float, default=0.7)
    a = p.parse_args()

    url = f"http://{a.host}:{a.port}{a.path_prefix}/v1/chat/completions"
    stop = time.time() + a.duration
    done, fails = [0], [0]
    lock = threading.Lock()

    def worker():
        while time.time() < stop:
            body = json.dumps({"model": a.model,
                               "messages": [{"role": "user", "content": a.prompt}],
                               "max_tokens": a.max_tokens, "temperature": a.temperature}).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=a.timeout).read()
                with lock:
                    done[0] += 1
            except Exception:
                with lock:
                    fails[0] += 1
                    time.sleep(2)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(a.concurrency)]
    [t.start() for t in ts]
    print(f"hammering {url} model={a.model} concurrency={a.concurrency} "
          f"duration={a.duration}s", flush=True)
    [t.join() for t in ts]
    print(f"done: ok={done[0]} errors={fails[0]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
