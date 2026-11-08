"""Interleaved A/B and contention probing for inference engine configurations.

Two claims this makes testable instead of arguable:

1. **"Config X is faster than config Y."** Variants are run alternately across
   rounds (round 0: A,B; round 1: B,A; ...). Thermal state, clock drift and
   background load then hit both arms equally, so a difference that survives
   alternation is a config effect and not a warm GPU. Measuring A, waiting
   twenty minutes, then measuring B is how most of these comparisons get
   published and is not a measurement.

2. **"The other workload does not interfere."** `probe` measures the same
   target with the competing engine idle and then saturated, and reports the
   delta. Whether an expert-streaming model on GPU 1 perturbs a
   VRAM-resident model on GPU 0 is a question about memory controllers and
   PCIe, not about intuition.

Nothing here is host-specific: each arm is described by shell templates with
`{port}` / `{name}` / `{log}` placeholders, so any launch method works - local
process, ssh, container, cluster submit. Site-specific specs stay out of the
repo (see ab.example.json; real ones go in ab.<site>.json, gitignored).
"""

import json
import os
import re
import shlex
import statistics
import subprocess
import threading
import time

from lib.engine import Probe
from lib import prompt as prompt_mod
from lib import report
from lib import util


class GpuSampler:
    """Poll a vendor CLI during measurement so every result carries its own proof.

    "The GPU is doing nothing" is a claim that needs samples, not a glance at a
    monitor: the load is bursty (prefill spikes, then a quieter decode phase) and
    a dashboard viewed between arms will show an idle card. The sampler records
    utilization and VRAM per card across the whole session, and the run reports
    the peak - which also catches the failure mode where the model silently
    offloads to CPU and still returns plausible numbers.

    The command is an operator template (portable, host-agnostic); output is
    parsed for percentages and MiB/GB figures generically.
    """

    def __init__(self, template, interval=3.0, ctx=None):
        self.template, self.interval, self.ctx = template, interval, ctx or {}
        self.samples, self._stop, self._th = [], False, None

    def start(self):
        if not self.template:
            return
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self):
        while not self._stop:
            out = shell(render(self.template, self.ctx), 20)
            if out:
                self.samples.append({"t": round(time.time()), "raw": out[:600]})
            time.sleep(self.interval)

    def stop(self):
        self._stop = True
        if self._th:
            self._th.join(timeout=10)

    def summary(self):
        """{card: {peak_util_pct, peak_vram_mib, samples}} - peaks over the session.

        JSON output (rocm-smi --json, nvidia-smi --query-gpu) is parsed per card
        exactly; anything else falls back to scanning for percentages and
        MiB/GB/byte figures, which is a coarse "something happened on a card"
        indicator rather than a per-card attribution.
        """
        res = {}

        def bump(card, util=None, vram=None):
            d = res.setdefault(card, {"peak_util_pct": 0, "peak_vram_mib": 0, "samples": 0})
            d["samples"] += 1
            if util is not None:
                d["peak_util_pct"] = max(d["peak_util_pct"], float(util))
            if vram is not None:
                d["peak_vram_mib"] = max(d["peak_vram_mib"], float(vram))

        for s in self.samples:
            raw = s["raw"]
            try:
                d = json.loads(raw)
            except Exception:
                d = None
            if isinstance(d, dict):
                parsed = False
                for k, v in d.items():
                    if not isinstance(v, dict):
                        continue
                    m = re.match(r"card(\d+)|gpu?(\d+)", str(k), re.I)
                    if not m:
                        continue
                    card = "card" + (m.group(1) or m.group(2))
                    util = v.get("GPU use (%)") or v.get("utilization.gpu") or v.get("use(%)")
                    used = (v.get("VRAM Total Used Memory (B)") or v.get("memory.used")
                            or v.get("Used Memory"))
                    vram = None
                    if used is not None:
                        used = float(str(used).split()[0])
                        vram = used / 1048576 if used > 1e6 else used
                    bump(card, util, vram)
                    parsed = True
                if parsed:
                    continue
            util = re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", raw)
            vram = re.findall(r"(\d+)\s*(?:MiB|M iB)", raw) or \
                [str(int(x) * 1024) for x in re.findall(r"(\d+)\s*GB", raw)] or \
                [x for x in re.findall(r"\b(\d{9,12})\b", raw)]  # plain bytes
            for card in re.findall(r"card(\d+)", raw) or re.findall(r"GPU\s*\[?\s*(\d+)", raw):
                bump("card" + card, util[0] if util else None,
                     float(vram[0]) / 1048576 if vram and float(vram[0]) > 1e6 else (vram[0] if vram else None))
        return res

    def peak_util(self):
        s = self.summary()
        return max((d["peak_util_pct"] for d in s.values()), default=0)


def render(template, ctx):
    """Substitute the known {port}/{name}/{log}/{model}/{host}/{pid} placeholders.

    Works on both string and list templates. str.format() is deliberately
    avoided: ready commands routinely contain curl's `%{http_code}`, which
    format() would try to interpolate.
    """
    if not template:
        return template
    if isinstance(template, (list, tuple)):
        return [render(t, ctx) for t in template]
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def teardown(arm, ctx):
    """Tear down an arm: explicit template, else kill the recorded PID.

    Killing by recorded PID is the default because pattern-based kills are a
    footgun: `pkill -f -- --port 5806` also matches the shell that is running
    that very command, so it terminates itself before the new server starts.
    The bracket idiom (`--port[ ]5806`) avoids the self-match when a pattern is
    genuinely needed.
    """
    if arm.get("teardown"):
        return shell(render(arm["teardown"], ctx), 60)
    if ctx.get("pid"):
        return shell(render("kill {pid} 2>/dev/null || true", ctx), 30)
    return ""


_POSIX_SHELL = None


def posix_shell():
    """Locate a POSIX shell for string templates (Windows has no usable cmd.exe here).

    Templates are written for a POSIX shell: they use single quotes, `>`, `&`,
    `$!`. cmd.exe does not understand single quotes, so it interprets the
    redirection itself - the remote command arrives truncated and the launch
    silently no-ops. That failure looks exactly like "the GPUs are idle, nothing
    is happening", so string templates are always run through a real POSIX shell
    when one exists (Git for Windows' bash counts). Set PERF_BENCH_SHELL to
    override. List-form templates need no shell at all and are the portable
    choice.
    """
    global _POSIX_SHELL
    if _POSIX_SHELL is not None:
        return _POSIX_SHELL
    import shutil
    cand = [os.environ.get("PERF_BENCH_SHELL"), shutil.which("bash"), shutil.which("sh"),
            r"C:\Program Files\Git\bin\bash.exe", "/bin/sh"]
    _POSIX_SHELL = next((c for c in cand if c and os.path.exists(c)), None)
    return _POSIX_SHELL


def shell(cmd, timeout=60):
    """Run a template. List/tuple = direct exec (no shell quoting); string = POSIX shell."""
    if not cmd:
        return ""
    try:
        if isinstance(cmd, (list, tuple)):
            p = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        else:
            ps = posix_shell()
            if ps:
                p = subprocess.run([ps, "-c", cmd], capture_output=True, text=True, timeout=timeout)
            else:
                p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


def wait_ready(probe, arm, ctx, timeout):
    """Poll the arm's /health until 200, or until the ready command says so.

    Model load takes a minute or more on this class of hardware, so the wait is
    logged: silence here is indistinguishable from a hang otherwise.
    """
    t0, next_note = time.time(), 0.0
    while time.time() - t0 < timeout:
        if arm.get("ready"):
            out = shell(render(arm["ready"], ctx), 30)
            if out.strip().endswith("200") or "ok" in out.lower():
                util.log(f"    ready after {time.time() - t0:.0f}s")
                return True
        else:
            try:
                import urllib.request
                if urllib.request.urlopen(probe.base + probe.path_prefix + "/health",
                                          timeout=10).getcode() == 200:
                    util.log(f"    ready after {time.time() - t0:.0f}s")
                    return True
            except Exception:
                pass
        if time.time() > next_note:
            util.log(f"    waiting for arm to come up... {time.time() - t0:.0f}s")
            next_note = time.time() + 20
        time.sleep(3)
    return False


def check_identity(probe, expected):
    """Confirm the port serves the model we think it does.

    A port left occupied by a server from an earlier run will happily answer
    /health and return plausible-looking numbers for a *different* engine
    build, quant or drafter config. That is the single easiest way to publish a
    fake result, so the identity is asserted rather than assumed.
    """
    try:
        import urllib.request
        props = json.loads(urllib.request.urlopen(probe.base + probe.path_prefix + "/props",
                                                  timeout=15).read())
    except Exception as e:
        return {"ok": False, "error": f"/props unreachable: {type(e).__name__}"}
    # Field names differ across llama.cpp builds and forks: newer builds expose
    # model_alias/model_path/build_info, older ones loaded_model_id/model. Taking
    # only one name silently yields "" , and an empty identity makes the check
    # vacuously pass - which is exactly how a stale server gets measured as if it
    # were the arm under test.
    got = ""
    for k in ("loaded_model_id", "model", "model_alias", "model_path", "display_name"):
        v = props.get(k)
        if isinstance(v, str) and v:
            got = v
            break
    cands = {got, got.rsplit("/", 1)[-1]}
    if isinstance(props.get("model_path"), str):
        cands.add(props["model_path"].rsplit("/", 1)[-1])
    if isinstance(props.get("model_alias"), str):
        cands.add(props["model_alias"].rsplit("/", 1)[-1])
    cands = {c.lower().replace(".gguf", "") for c in cands if c}
    # A test server started directly from a GGUF reports a filesystem path, while
    # a gateway alias is a short name - so compare on basenames, not exact strings.
    want = expected.lower().replace(".gguf", "")
    base = want.rsplit("/", 1)[-1]
    if expected and not any(want in c or base in c or c in want for c in cands):
        return {"ok": False, "error": f"port serves '{sorted(cands)}', expected '{expected}' "
                                      f"- stale server on this port?"}
    if not got:
        return {"ok": False, "error": "/props returned no model identity "
                                      "(unrecognized field names) - cannot verify the arm"}
    build = ""
    for k in ("build_info", "build", "commit", "version"):
        v = props.get(k)
        if isinstance(v, str) and v:
            build = (build + " " + v).strip() if k in ("build", "commit") and build else v
            if k == "build_info":
                break
    return {"ok": True, "model": got, "build": build,
            "ftype": props.get("model_ftype"), "total_tokens": props.get("total_tokens")}


def compact_engine(ident, version_out=""):
    """One-line engine identity for the CSV: build string + quant if known.

    `version` templates often point at /props, which returns the entire server
    configuration as a blob. Dumped into a CSV column it buries the one fact
    that matters (which build produced this number), so the blob is parsed down
    to build_info/build/commit; only genuinely free-text output is kept as-is.
    """
    parts = []
    b = (ident or {}).get("build") or ""
    if b:
        parts.append(b)
    ft = (ident or {}).get("ftype")
    if ft:
        parts.append(str(ft))
    if version_out and not version_out.lstrip().startswith(("{", "[")):
        parts.append(version_out.strip()[:100])
    if not parts and version_out:
        try:
            d = json.loads(version_out)
            for k in ("build_info", "build", "commit", "version"):
                if isinstance(d.get(k), str):
                    parts.append(d[k])
                    break
        except Exception:
            parts.append(version_out.strip()[:100])
    return " | ".join(dict.fromkeys(parts))[:160]


def check_args(spec, arm, ctx):
    """Verify the process on the port was started with *this* arm's flags.

    /props identifies the model, not the drafter configuration - and a stale
    server from an earlier run serves the same model with different
    --spec-draft-* values, which produces a plausible result for the wrong arm.
    When the spec provides a `cmdline` template (typically reading
    /proc/<pid>/cmdline on the server), every flag this arm declares must be
    present in the live process, or the arm is rejected.
    """
    tmpl = spec.get("cmdline")
    if not tmpl or not arm.get("args"):
        return {"ok": True, "skipped": True}
    live = shell(render(tmpl, ctx), 30)
    if not live.strip():
        return {"ok": False, "error": "cmdline probe returned nothing (no process on port?)"}
    tokens = [t for t in shlex.split(arm["args"]) if t.startswith("-")]
    missing = [t for t in tokens if t not in live]
    if missing:
        return {"ok": False, "error": f"live process is missing this arm's flags: {missing} "
                                      f"- stale server, or launch did not take effect"}
    return {"ok": True, "cmdline": live[:400]}


def measure(arm, spec, args, port):
    """Launch one arm, measure a full session, tear it down."""
    ep = spec["endpoint"]
    ctx = {"port": port, "name": arm["name"], "log": f"pb-ab-{arm['name']}",
           "model": ep.get("model", ""), "host": ep.get("host", "127.0.0.1"), "pid": ""}
    out = {"arm": arm["name"], "args": arm.get("args", "")}
    # Pre-clean in its own call. Never put a pattern kill and the launch in the
    # same command line: the launcher's own cmdline then contains both the
    # pattern and the literal `--port 5806` being started, so pkill matches the
    # shell that is about to start the server and kills it first. The launch
    # then silently no-ops and the GPUs sit idle.
    if arm.get("launch") and (arm.get("prekill") or arm.get("teardown")):
        shell(render(arm.get("prekill") or arm["teardown"], ctx), 60)
        time.sleep(3)
    if arm.get("launch"):
        out_res = shell(render(arm["launch"], ctx), 60)
        m = re.search(r"STARTED_PID=(\d+)", out_res) or re.search(r"^(\d+)$", out_res.strip())
        if m:
            ctx["pid"] = m.group(1)
            out["pid"] = ctx["pid"]
        else:
            out["error"] = f"launch produced no PID (output: {out_res[:160]!r}) - " \
                           "the launch command likely killed its own shell, or the shell " \
                           "could not run it"
            util.log("  " + out["error"])
            return out
    probe = Probe(f"{ep.get('scheme','http')}://{ep.get('host','127.0.0.1')}:{port}",
                  ep.get("api_key", ""), args.timeout, ep.get("path_prefix", ""))
    if not wait_ready(probe, arm, ctx, arm.get("ready_timeout", args.ready_timeout)):
        out["error"] = "arm never became ready"
        util.log("  " + out["error"] + "\n  log tail: "
                 + shell(render(arm.get("logtail", ""), ctx), 30)[-400:])
        teardown(arm, ctx)
        return out
    ident = check_identity(probe, spec.get("identity_model") or ep.get("model", ""))
    if not ident["ok"]:
        out["error"] = ident["error"]
        util.log("  " + out["error"])
        teardown(arm, ctx)
        return out
    out["served_model"], out["build"] = ident["model"], ident.get("build", "")
    argcheck = check_args(spec, arm, ctx)
    if not argcheck["ok"]:
        out["error"] = argcheck["error"]
        util.log("  " + out["error"])
        teardown(arm, ctx)
        return out
    out["flags_verified"] = not argcheck.get("skipped", False)
    text, approx = prompt_mod.build(args.prompt_tokens, probe.base)
    util.log(f"    prompt calibrated: {approx} tokens")
    gp = GpuSampler(spec.get("gpu_sample"), ctx=ctx)
    gp.start()
    s = probe.measure_session(ep.get("model", ""), text, reps=args.reps, gen=args.gen,
                              progress=lambda m: util.log("    " + m))
    gp.stop()
    out["gpu"] = gp.summary()
    peak = gp.peak_util()
    util.log(f"    gpu during measurement: {out['gpu'] or 'no sampler configured'}")
    if spec.get("gpu_sample") and peak < 5:
        out["gpu_suspect"] = True
        util.log("    ! GPU utilization stayed under 5% - the model may not be on the GPU")
    out.update({"prompt_tokens": s["prompt_tokens"], "prefill": s["prefill"],
                "decode": s["decode"], "mtp_acc": s["mtp_acc"],
                "draft_per_out": s["draft_per_out"], "acc_per_out": s["acc_per_out"],
                "cache_bust_ok": s["cache_bust_ok"], "source": s["source"],
                # The engine column must identify the *build*, not dump the whole
                # /props blob: it lands in runs.csv next to every metric, and a
                # 200-char settings blob makes the CSV unreadable. build+commit
                # from /props is the compact identity; the arm's own `version`
                # template remains the fallback for engines without those fields.
                "engine": compact_engine(ident, shell(render(arm.get("version", ""), ctx), 30))})
    teardown(arm, ctx)
    time.sleep(3)
    return out


def aggregate(runs):
    """Median over rounds per arm, plus delta against the first arm listed."""
    by = {}
    for r in runs:
        by.setdefault(r["arm"], []).append(r)
    agg = {}
    for name, rs in by.items():
        good = [r for r in rs if "error" not in r]
        if not good:
            agg[name] = {"error": "all rounds failed", "rounds": len(rs)}
            continue
        accs = [r["mtp_acc"] for r in good if r.get("mtp_acc")]
        dpo = [r["draft_per_out"] for r in good if r.get("draft_per_out")]
        agg[name] = {
            "prefill": round(statistics.median([r["prefill"]["median"] for r in good]), 1),
            "decode": round(statistics.median([r["decode"]["median"] for r in good]), 2),
            "prefill_spread_pct": round(statistics.median([r["prefill"]["spread_pct"] for r in good]), 1),
            "decode_spread_pct": round(statistics.median([r["decode"]["spread_pct"] for r in good]), 1),
            "mtp_acc": round(statistics.median(accs), 4) if accs else None,
            # Reported alongside acceptance because acceptance alone is not the
            # goal: a drafter can raise acc while spending more per draft step
            # and end up slower. draft_per_out is that cost term.
            "draft_per_out": round(statistics.median(dpo), 3) if dpo else None,
            "rounds_ok": len(good), "rounds": len(rs)}
    ref = next((n for n in agg if "error" not in agg[n]), None)
    if ref:
        for n, v in agg.items():
            if "error" in v or n == ref:
                continue
            v["decode_delta_pct"] = round((v["decode"] - agg[ref]["decode"]) / agg[ref]["decode"] * 100, 1)
            v["prefill_delta_pct"] = round((v["prefill"] - agg[ref]["prefill"]) / agg[ref]["prefill"] * 100, 1)
    return agg, ref


def print_agg(agg, ref):
    util.log("\n=== aggregate over rounds (median) ===")
    for n, v in agg.items():
        if "error" in v:
            util.log(f"  {n:<16} FAILED ({v['error']})")
            continue
        d = f"  decode {v['decode_delta_pct']:+5.1f}%" if "decode_delta_pct" in v else ""
        util.log(f"  {n:<16} prefill={v['prefill']:8.1f} (spread {v['prefill_spread_pct']:4.1f}%)  "
                 f"decode={v['decode']:6.2f} (spread {v['decode_spread_pct']:4.1f}%){d}  "
                 f"mtp_acc={v['mtp_acc']} draft/out={v.get('draft_per_out')}  "
                 f"[{v['rounds_ok']}/{v['rounds']} rounds]")
        if v["decode_spread_pct"] > 10:
            util.log(f"  {'':16} ! LOW CONFIDENCE: decode spread >10% - raise --reps or check for contention")


def mode_ab(spec, args, rows):
    arms = spec["arms"]
    runs = []
    for rnd in range(args.rounds):
        order = arms if rnd % 2 == 0 else list(reversed(arms))  # alternate to cancel drift
        for arm in order:
            util.log(f"round {rnd}: arm {arm['name']}")
            r = measure(arm, spec, args, args.port)
            r["round"] = rnd
            runs.append(r)
            if "error" in r:
                util.log("  " + r["error"])
            else:
                util.log(f"  prefill={r['prefill']['median']} decode={r['decode']['median']} "
                         f"mtp_acc={r['mtp_acc']} cache_bust={r['cache_bust_ok']}")
    agg, ref = aggregate(runs)
    print_agg(agg, ref)
    for r in runs:
        if "error" in r:
            continue
        rows.append({"test": "ab", "phase": "decode-warm", "depth": r["prompt_tokens"],
                     "metric": "decode_tps", "value": r["decode"]["median"],
                     "variant": r["arm"], "engine": r.get("engine", ""),
                     "detail": f"round={r['round']} spread={r['decode']['spread_pct']}% "
                               f"src={r['source']}"})
        rows.append({"test": "ab", "phase": "prefill-cold", "depth": r["prompt_tokens"],
                     "metric": "prefill_tps", "value": r["prefill"]["median"],
                     "variant": r["arm"], "detail": f"round={r['round']} spread={r['prefill']['spread_pct']}% "
                                                    f"cache_bust={r['cache_bust_ok']}"})
        if r.get("mtp_acc"):
            rows.append({"test": "ab", "phase": "decode-warm", "depth": r["prompt_tokens"],
                         "metric": "mtp_acc", "value": r["mtp_acc"], "variant": r["arm"],
                         "detail": f"draft_per_out={r.get('draft_per_out')} "
                                   f"acc_per_out={r.get('acc_per_out')}"})
    return {"rounds": runs, "aggregate": agg, "reference": ref}


def mode_probe(spec, args, rows):
    """Measure one arm with the interfering workload idle, then saturated."""
    arm, interf = spec["arms"][0], spec.get("interference")
    if not interf:
        util.log("spec has no 'interference' block - nothing to probe")
        return {}
    ep = spec["endpoint"]
    ctx = {"port": args.port, "name": arm["name"], "log": f"pb-probe-{arm['name']}",
           "model": ep.get("model", ""), "host": ep.get("host", "127.0.0.1"), "pid": ""}
    if arm.get("launch"):
        if arm.get("prekill") or arm.get("teardown"):
            shell(render(arm.get("prekill") or arm["teardown"], ctx), 60)
            time.sleep(3)
        shell(render(arm["launch"], ctx), 60)
    probe = Probe(f"{ep.get('scheme','http')}://{ep.get('host','127.0.0.1')}:{args.port}",
                  ep.get("api_key", ""), args.timeout, ep.get("path_prefix", ""))
    if not wait_ready(probe, arm, ctx, args.ready_timeout):
        util.log("target never became ready")
        return {}
    ident = check_identity(probe, spec.get("identity_model") or ep.get("model", ""))
    if not ident["ok"]:
        util.log(ident["error"])
        return {}
    text, _ = prompt_mod.build(args.prompt_tokens, probe.base)
    gp_idle = GpuSampler(spec.get("gpu_sample"), ctx=ctx)
    gp_idle.start()
    idle = probe.measure_session(ep.get("model", ""), text, reps=args.reps, gen=args.gen,
                                 progress=lambda m: util.log("  idle " + m))
    gp_idle.stop()
    idle["gpu"] = gp_idle.summary()
    util.log(f"idle:  prefill={idle['prefill']['median']} decode={idle['decode']['median']} "
             f"mtp_acc={idle['mtp_acc']} gpu={idle['gpu']}")
    util.log(f"starting interference: {interf['name']}")
    shell(render(interf["start"], ctx), 120)
    time.sleep(interf.get("warmup_s", 25))
    gp_busy = GpuSampler(spec.get("gpu_sample"), ctx=ctx)
    gp_busy.start()
    busy = probe.measure_session(ep.get("model", ""), text, reps=args.reps, gen=args.gen,
                                 progress=lambda m: util.log("  busy " + m))
    gp_busy.stop()
    shell(render(interf.get("stop", ""), ctx), 60)
    busy["gpu"] = gp_busy.summary()
    util.log(f"busy:  prefill={busy['prefill']['median']} decode={busy['decode']['median']} "
             f"mtp_acc={busy['mtp_acc']} gpu={busy['gpu']}")
    di, db = idle["decode"]["median"], busy["decode"]["median"]
    pct = (db - di) / di * 100 if di else 0
    verdict = "MEANINGFUL INTERFERENCE" if abs(pct) > 5 else "no meaningful interference"
    util.log(f"\n=== contention: decode {di} -> {db} ({pct:+.1f}%) : {verdict}")
    for phase, s in (("idle", idle), ("interference-busy", busy)):
        rows.append({"test": "probe", "phase": phase, "depth": s["prompt_tokens"],
                     "metric": "decode_tps", "value": s["decode"]["median"],
                     "detail": f"side={interf['name']} spread={s['decode']['spread_pct']}% "
                               f"gpu={json.dumps(s.get('gpu', {}))[:120]}"})
        rows.append({"test": "probe", "phase": phase, "depth": s["prompt_tokens"],
                     "metric": "prefill_tps", "value": s["prefill"]["median"],
                     "detail": f"side={interf['name']} spread={s['prefill']['spread_pct']}%"})
    return {"idle": idle, "busy": busy, "delta_pct": round(pct, 1), "verdict": verdict}


def run(spec_path, args):
    spec = util.read_structured(spec_path)
    if not spec:
        util.die(f"cannot read spec {spec_path}")
    args.port = args.port or spec.get("port", 8080)
    args.ready_timeout = args.ready_timeout or spec.get("ready_timeout", 420)
    rows, out = [], {}
    if args.mode == "ab":
        if len(spec.get("arms", [])) < 2:
            util.die("ab mode needs at least 2 arms")
        out = mode_ab(spec, args, rows)
    else:
        out = mode_probe(spec, args, rows)
    if rows:
        run_id = time.strftime("%Y%m%d-%H%M%S")
        report.save(rows, args.out or "results", args.tag or args.mode, run_id)
        out["csv"] = "results/runs.csv"
    util.log(json.dumps(out.get("aggregate", out.get("verdict", "")), indent=1))
    return 0
