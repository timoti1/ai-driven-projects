"""OpenAI-compatible endpoint probes and llama-bench wrapper."""
import json
import re
import statistics
import subprocess
import time
import urllib.request
import uuid

from lib import prompt as prompt_mod
from lib import util

CORPUS_UNIT = ("The quick brown fox reviews the quarterly logistics report of the "
               "distribution hub while the engineering team debates cache invalidation, "
               "tile ordering, and GPU kernel fusion strategies for inference servers. ")


def corpus_tokens(n, chars_per_token=4):
    need = max(n * chars_per_token, 40)
    return (CORPUS_UNIT * (need // len(CORPUS_UNIT) + 1))[:need]


class Probe:
    def __init__(self, base, api_key="", timeout=600, path_prefix=""):
        self.base = base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.path_prefix = path_prefix

    def _post(self, path, body, stream=False):
        req = urllib.request.Request(self.base + self.path_prefix + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + self.api_key} if self.api_key else {})})
        return time.time(), urllib.request.urlopen(req, timeout=self.timeout)

    def _chat(self, prompt, max_tokens, temperature=0.0, stream=False):
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature}
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        return self._post("/v1/chat/completions", body)

    # ---- single-call measurement (preferred path) -------------------------
    #
    # llama.cpp reports its own counters in `timings`: prompt_per_second and
    # predicted_per_second exclude HTTP/queue time, and `cache_n` says how much
    # of the prompt was *not* recomputed. Whenever those counters exist they are
    # used, and the wall-clock derivation is only a fallback for servers that do
    # not expose them. `draft_n` / `draft_n_accepted` are what make a
    # speculative-decoding comparison interpretable at all: decode tok/s on its
    # own cannot tell a better drafter from a lazier one.
    def chat_once(self, model, prompt, max_tokens, temperature=0.0, seed=42):
        self.model = model
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature, "seed": seed,
                "stream": False}
        t0 = time.time()
        try:
            d = json.loads(self._post("/v1/chat/completions", body)[1].read())
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "wall_s": round(time.time() - t0, 2)}
        wall = time.time() - t0
        t, u = d.get("timings") or {}, d.get("usage") or {}
        server = bool(t)
        prompt_n = int(t.get("prompt_n") or u.get("prompt_tokens") or 0)
        cache_n = int(t.get("cache_n") or 0)
        gen_n = int(t.get("predicted_n") or u.get("completion_tokens") or 0)
        prefill = t.get("prompt_per_second") or 0.0
        decode = t.get("predicted_per_second") or 0.0
        if not prefill and prompt_n:
            prefill = prompt_n / max(wall, 0.01)
        if not decode and gen_n and prefill:
            decode = gen_n / max(wall - prompt_n / prefill, 0.05)
        msg = (d.get("choices") or [{}])[0].get("message", {})
        return {"wall_s": round(wall, 2), "prompt_n": prompt_n, "cache_n": cache_n,
                "prefill_tps": round(prefill, 2), "gen_n": gen_n,
                "decode_tps": round(decode, 2),
                "draft_n": int(t.get("draft_n") or 0),
                "draft_acc": int(t.get("draft_n_accepted") or 0),
                "source": "server-timings" if server else "derived",
                "out_chars": len((msg.get("content") or "") + (msg.get("reasoning_content") or ""))}

    # ---- one measurement session -----------------------------------------
    #
    # prefill is measured on a *cache-cold* prompt (front nonce, generation
    # suppressed); decode is measured on the byte-identical prompt *after* a
    # warm-up call so the KV prefix is resident. Each side is asserted: a
    # prefill rep that reports a large cache_n is flagged rather than averaged
    # in, and reps are reported with spread instead of a single number.
    def measure_session(self, model, prompt, reps=3, gen=1024, warm=True, settle=True,
                        progress=None):
        if settle:
            self.chat_once(model, prompt, min(64, max(gen // 8, 8)))
        cold = []
        for i in range(reps):
            c = self.chat_once(model, prompt_mod.front_nonce(prompt), 8)
            if "error" not in c:
                cold.append(c)
            if progress:
                progress(f"prefill rep {i + 1}/{reps}: {c.get('prefill_tps', 0)} t/s "
                         f"(prompt_n={c.get('prompt_n', 0)} cache_n={c.get('cache_n', 0)})")
        for c in cold:
            if c["prompt_n"] and c["cache_n"] > c["prompt_n"] * 0.2:
                c["cache_suspect"] = True
        if warm:
            self.chat_once(model, prompt, gen)
        warm_runs = []
        for i in range(reps):
            w = self.chat_once(model, prompt, gen)
            if "error" not in w:
                warm_runs.append(w)
            if progress:
                progress(f"decode rep {i + 1}/{reps}: {w.get('decode_tps', 0)} t/s "
                         f"(gen_n={w.get('gen_n', 0)} draft={w.get('draft_n', 0)} "
                         f"acc={w.get('draft_acc', 0)})")
        draft = sum(w["draft_n"] for w in warm_runs)
        acc = sum(w["draft_acc"] for w in warm_runs)
        gen_n = max(sum(w["gen_n"] for w in warm_runs), 1)
        return {
            "reps": reps, "gen_target": gen,
            "prefill": spread(cold, "prefill_tps"), "prefill_runs": cold,
            "decode": spread(warm_runs, "decode_tps"), "decode_runs": warm_runs,
            # Acceptance of what the drafter proposed (llama.cpp semantics:
            # draft_n = tokens proposed, draft_n_accepted = tokens kept). Named
            # per-output rather than "mean draft length": the ratio of proposed
            # tokens to emitted tokens is the drafting *cost*, and a longer mean
            # draft length is not derivable from these two counters alone.
            "mtp_acc": round(acc / draft, 4) if draft else None,
            "draft_tokens": draft,
            "draft_per_out": round(draft / gen_n, 3) if draft else None,
            "acc_per_out": round(acc / gen_n, 3) if draft else None,
            "cache_bust_ok": bool(cold) and all(not c.get("cache_suspect") for c in cold),
            "prompt_tokens": (cold[0]["prompt_n"] if cold else 0),
            "source": (warm_runs[0]["source"] if warm_runs else "n/a"),
        }

    def run_case(self, name, suite, model, spec, params):
        self.model = model
        t = spec.get("type")
        rows = []
        if t == "health":
            rows.append(self.case_health(name, suite))
        elif t == "prefill":
            sizes = params["pp_sizes"] if params.get("force_pp") else (spec.get("tokens") or spec.get("sweep_values") or params["pp_sizes"])
            if not isinstance(sizes, list):
                sizes = [sizes]
            for n in sizes:
                rows.append(self.case_prefill(name, suite, model, int(n), spec))
        elif t == "decode":
            depths = params["depths"] if params.get("force_depths") else (spec.get("context_depth") or spec.get("sweep_values") or params["depths"])
            if not isinstance(depths, list):
                depths = [depths]
            for d in depths:
                rows.append(self.case_decode(name, suite, model, int(d), spec))
        elif t == "kv-cache":
            rows.extend(self.case_kv_cache(name, suite, model, spec, params))
        elif t == "spec-decode":
            rows.extend(self.case_spec_decode(name, suite, model, spec, params))
        else:
            util.die(f"unknown case type '{t}' in {suite}/{name}")
        return [r for r in rows if r]

    def case_health(self, name, suite):
        t0 = time.time()
        try:
            r = urllib.request.urlopen(self.base + self.path_prefix + "/health", timeout=15)
            ok, code = True, r.getcode()
        except Exception:
            ok, code = False, None
        dt_h = time.time() - t0
        t1 = time.time()
        try:
            r = urllib.request.urlopen(self.base + self.path_prefix + "/v1/models", timeout=15)
            data = json.load(r)
            ids = [m.get("id") for m in data.get("data", [])]
        except Exception as e:
            ids, err = [], str(e)
        return {"test": suite + "/" + name, "phase": "health", "depth": 0,
                "metric": "health_ok", "value": 1 if ok else 0,
                "detail": f"code={code} health_s={dt_h:.3f} models={','.join(ids[:8])[:180]}"}

    def case_prefill(self, name, suite, model, tokens, spec):
        cpt = spec.get("chars_per_token", 4)
        # nonce first: a trailing nonce leaves the prefix cached and the number
        # becomes a cache hit, not a prefill measurement
        prompt = f"P{uuid.uuid4().hex[:8]} " + corpus_tokens(tokens, cpt)
        try:
            t0, r = self._chat(prompt, 1)
            dt = time.time() - t0
            d = json.load(r)
            t, u = d.get("timings") or {}, d.get("usage") or {}
            pt = int(t.get("prompt_n") or u.get("prompt_tokens") or len(prompt) // cpt)
            val = round(t.get("prompt_per_second") or pt / max(dt, 0.01), 1)
            cache_n = int(t.get("cache_n") or 0)
            return {"test": suite + "/" + name, "phase": "prefill", "depth": pt,
                    "metric": "prefill_tps", "value": val,
                    "detail": (f"target={tokens} prompt_tokens={pt} cache_n={cache_n} "
                               f"elapsed={dt:.2f}s src={'server' if t else 'derived'}")}
        except Exception as e:
            return {"test": suite + "/" + name, "phase": "prefill", "depth": tokens,
                    "metric": "prefill_tps", "value": 0, "detail": f"error={type(e).__name__}"}

    def case_decode(self, name, suite, model, depth, spec):
        cpt = spec.get("chars_per_token", 4)
        n = spec.get("tokens", 128)
        prompt = f"D{uuid.uuid4().hex[:8]} " + corpus_tokens(max(depth - 64, 64), cpt) + "\nAnswer briefly."
        try:
            t0, r = self._chat(prompt, n, temperature=0.6, stream=True)
            first = None
            comp = 0
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data:") or "[DONE]" in line:
                    continue
                try:
                    c = json.loads(line[5:])
                except Exception:
                    continue
                if (c.get("usage") or {}).get("completion_tokens"):
                    comp = c["usage"]["completion_tokens"]
                d = (c.get("choices") or [{}])[0].get("delta", {})
                for k in ("content", "reasoning_content"):
                    if d.get(k):
                        if first is None:
                            first = time.time() - t0
            total = time.time() - t0
            gen = max(total - (first or 0), 0.05)
            return {"test": suite + "/" + name, "phase": "decode", "depth": depth,
                    "metric": "decode_tps", "value": round((comp or n) / gen, 1),
                    "first_token_s": round(first or -1, 2),
                    "detail": f"first_token_s={first or -1:.2f} total_s={total:.2f} completion={comp or n}"}
        except Exception as e:
            return {"test": suite + "/" + name, "phase": "decode", "depth": depth,
                    "metric": "decode_tps", "value": 0, "detail": f"error={type(e).__name__}"}

    def case_spec_decode(self, name, suite, model, spec, params):
        """Long-context decode with speculative decoding fully accounted for.

        This is the case to use when comparing drafter settings
        (--spec-draft-n-max / --spec-draft-p-min and equivalents): a decode
        number without an acceptance rate cannot distinguish a better drafter
        from one that merely guesses more often.
        """
        target = spec.get("prompt_tokens", params.get("prompt_tokens", 8000))
        gen = spec.get("tokens", 1024)
        reps = spec.get("reps", params.get("repeat", 3))
        text, approx = prompt_mod.build(target, self.base)
        s = self.measure_session(model, text, reps=reps, gen=gen,
                                 warm=spec.get("cache", "warm") == "warm")
        base = {"test": suite + "/" + name, "depth": s["prompt_tokens"],
                "detail": f"reps={reps} gen={gen} src={s['source']} "
                          f"calibrated={'tokenize' if approx and abs(approx - s['prompt_tokens']) < approx * 0.1 else 'heuristic'}"}
        rows = [
            {**base, "phase": "prefill-cold", "metric": "prefill_tps", "value": s["prefill"]["median"],
             "detail": base["detail"] + f" spread={s['prefill']['spread_pct']}% cache_bust={s['cache_bust_ok']}"},
            {**base, "phase": "decode-warm", "metric": "decode_tps", "value": s["decode"]["median"],
             "detail": base["detail"] + f" spread={s['decode']['spread_pct']}%"},
        ]
        if s["mtp_acc"] is not None:
            rows.append({**base, "phase": "decode-warm", "metric": "mtp_acc", "value": s["mtp_acc"],
                         "detail": f"draft_tokens={s['draft_tokens']} "
                                   f"draft_per_out={s['draft_per_out']} acc_per_out={s['acc_per_out']}"})
        else:
            rows.append({**base, "phase": "decode-warm", "metric": "mtp_acc", "value": 0,
                         "detail": "no draft counters reported (speculative decoding off, or not exposed)"})
        return rows

    def case_kv_cache(self, name, suite, model, spec, params):
        cpt = spec.get("chars_per_token", 4)
        prefix_n = spec.get("prefix_tokens") or max(params["pp_sizes"])
        hits = spec.get("hits", 3)
        out_tokens = spec.get("tokens", 32)
        prefix = "PREFIX-" + uuid.uuid4().hex[:10] + "\n" + corpus_tokens(prefix_n, cpt)
        rows = []
        try:
            t0, r = self._chat(prefix + "\nSummarize in one line.", 1)
            dt = time.time() - t0
            u = json.load(r).get("usage") or {}
            cold_pt = u.get("prompt_tokens") or len(prefix) // cpt
            cold = cold_pt / max(dt, 0.01)
            rows.append({"test": suite + "/" + name, "phase": "cache-cold-fill", "depth": cold_pt,
                         "metric": "prefill_tps", "value": round(cold, 1), "detail": f"prefix_tokens={prefix_n}"})
            best = 0
            for i in range(hits):
                t1, r2 = self._chat(prefix + f"\nQ{i} {uuid.uuid4().hex[:6]}: one line?", out_tokens)
                dt2 = time.time() - t1
                u2 = json.load(r2).get("usage") or {}
                hit = max(u2.get("prompt_tokens", 1), 1) * 1.0 / max(
                    (dt2 - out_tokens * 0.02), 0.01)  # prompt-side speed approximation
                best = max(best, hit)
            rows.append({"test": suite + "/" + name, "phase": "cache-hit", "depth": cold_pt,
                         "metric": "cache_hit_tps", "value": round(best, 1),
                         "detail": f"speedup_vs_cold={best / max(cold, 0.01):.1f}x hits={hits}"})
        except Exception as e:
            rows.append({"test": suite + "/" + name, "phase": "cache-hit", "depth": prefix_n,
                         "metric": "cache_hit_tps", "value": 0, "detail": f"error={type(e).__name__}"})
        return rows


def spread(runs, key):
    """median/min/max/spread for one metric across reps (>10% spread = low confidence)."""
    v = [r.get(key) or 0 for r in runs if r.get(key)]
    if not v:
        return {"median": 0.0, "min": 0.0, "max": 0.0, "spread_pct": 0.0, "n": 0}
    med = statistics.median(v)
    return {"median": round(med, 2), "min": round(min(v), 2), "max": round(max(v), 2),
            "spread_pct": round((max(v) - min(v)) / med * 100, 1) if med else 0.0, "n": len(v)}


ROW_RE = re.compile(r"\b(pp|tg)\s*(\d+)\b[^\d]*?([\d]+\.[\d]+)")


def run_llama_bench(exe, gguf, extra, tag, timeout):
    """Run llama.cpp's llama-bench binary and parse its pp/tg lines into rows."""
    cmd = [exe] + (["--model", gguf] if gguf else []) + (extra.split() if extra else [])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        text = p.stdout + "\n" + p.stderr
    except Exception as e:
        return [{"test": "llama-bench/run", "phase": "run", "depth": 0, "metric": "status",
                 "value": 0, "detail": f"error={e}"}]
    rows = []
    for kind, n, val in ROW_RE.findall(text):
        rows.append({"test": "llama-bench", "phase": kind, "depth": int(n),
                     "metric": f"{kind}_tps", "value": float(val), "detail": f"tag={tag}"})
    if not rows:
        rows.append({"test": "llama-bench", "phase": "parse", "depth": 0, "metric": "status",
                     "value": 0, "detail": "no pp/tg lines found; raw tail: " + text[-300:]})
    return rows
