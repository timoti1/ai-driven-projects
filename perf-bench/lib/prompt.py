"""Long, deterministic prompt construction with real token calibration.

Why this module exists
----------------------
Prompt length and cache state decide whether a number means anything:

* A trailing nonce does **not** defeat llama.cpp's prefix cache - the cache is
  matched from token 0, so everything before the nonce is served from cache and
  "prefill" collapses into a cache hit. The nonce has to go at the **front**.
* A short prompt never exercises long-context prefill or the KV path, and MTP
  acceptance measured on a 200-token prompt does not predict a 30K one.
* The prompt must be byte-identical between repetitions, otherwise the decode
  run is not measuring the same thing twice.

`build()` returns a deterministic prompt grown to a target token count,
calibrated against a live tokenizer via `/tokenize` when one is reachable
(llama.cpp exposes it on the server port), falling back to a chars/token
heuristic otherwise. `front_nonce()` is applied per measurement, never baked
into the stored prompt.
"""

import json
import urllib.request
import uuid

# A realistic coding task as the stable head of the prompt. Content is
# irrelevant to speed; it only needs to look like a real request so the model
# generates normally (and so MTP acceptance is representative).
SEED_DOC = """You are reviewing a data-ingestion service that is misbehaving in
production. Below is the codebase. Find every real defect, explain the failure
mode each one causes under load, and give a corrected implementation.

```python
class Source:
    def __init__(self, dsn, page=500):
        self.dsn, self.page, self.cursor = dsn, page, None

    def fetch(self, cursor=None, limit=None):
        conn = connect(self.dsn)            # per call
        rows = conn.query("select * from events where id > %s", cursor)
        return rows[: self.page]


class Deduplicator:
    def __init__(self):
        self.seen = []

    def filter(self, rows):
        out = []
        for r in rows:
            if r["id"] not in self.seen:
                self.seen.append(r["id"])
                out.append(r)
        return out


class Sink:
    def __init__(self, table):
        self.table = table

    def append(self, rows):
        for r in rows:
            conn.query(f"insert into {self.table} values (%s)", r["payload"])


def run(source, dedup, sink, stop_after=None):
    n = 0
    while True:
        rows = source.fetch(source.cursor)
        if not rows:
            return n
        rows = dedup.filter(rows)
        source.cursor = rows[-1]["id"] if rows else None
        sink.append(rows)
        n += len(rows)
        if stop_after and n >= stop_after:
            return n
```

Report findings as a numbered list. For each defect: severity, the observable
symptom, the root cause, and the fix. Then give the full corrected code. Cover
at minimum: connection handling, memory growth over long runs, correctness of
the cursor when a page is fully deduplicated, SQL construction, partial-write
behaviour on failure, and what happens when two processes run concurrently.
"""

# Deterministic filler: numbered synthetic modules. Index -> same bytes every
# time, so the prompt is byte-identical across runs (required for cache-warm
# decode and for comparing two engine configs against each other).
_MODULE_TMPL = """
### module_{n:03d}.py
```python
# Synthetic pipeline stage {n} - deterministic filler used only to grow context.
class Stage{n:03d}:
    def __init__(self, source, batch={batch}, retries=3):
        self.source = source
        self.batch = batch
        self.retries = retries
        self.state = {{"seen": set(), "rows": 0, "errors": []}}

    def read(self, cursor=None):
        rows = self.source.fetch(cursor=cursor, limit=self.batch)
        self.state["rows"] += len(rows)
        return rows

    def transform(self, rows):
        out = []
        for row in rows:
            key = row.get("id")
            if key is None or key in self.state["seen"]:
                continue
            self.state["seen"].add(key)
            row["stage"] = {n}
            row["value"] = float(row.get("value", 0)) * 1.0{suffix}
            out.append(row)
        return out

    def write(self, sink, rows):
        try:
            sink.append(rows)
        except Exception as exc:  # noqa: BLE001 - deliberate swallow (BUG)
            self.state["errors"].append(str(exc))
        return len(rows)
```
"""

CHARS_PER_TOKEN = 3.6  # rough average for Qwen-class BPE on code+prose


def tokenize(base, text, timeout=30):
    """Exact token count from a live llama.cpp server (/tokenize). None if absent."""
    try:
        body = json.dumps({"content": text, "add_bos": False}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/tokenize", data=body,
                                     headers={"Content-Type": "application/json"})
        return len(json.loads(urllib.request.urlopen(req, timeout=timeout).read())["tokens"])
    except Exception:
        return None


def build(target_tokens=8000, base=None, chunk=6, cap=400):
    """Return (prompt_text, token_estimate). Calibrated when `base` is reachable."""
    body = SEED_DOC.rstrip()
    n, grown = 0, 0
    tokens = tokenize(base, body) if base else None
    while (tokens if tokens is not None else int(len(body) / CHARS_PER_TOKEN)) < target_tokens and n < cap:
        for _ in range(chunk):
            body += _MODULE_TMPL.format(n=n, batch=250 + n, suffix=f"{n % 7}")
            n += 1
        grown += chunk
        if tokens is not None:
            tokens = tokenize(base, body)
    if tokens is None:
        tokens = int(len(body) / CHARS_PER_TOKEN)
    return body, tokens


def front_nonce(prompt, nonce=None):
    """Cache-busting nonce at the FRONT: invalidates the whole prefix, not the tail."""
    return f"[bench-nonce {nonce or uuid.uuid4().hex}]  {prompt}"
