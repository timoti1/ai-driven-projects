"""Summary report for all benchmarked models.

Usage:
    python3 report.py

Reads:
    bench/results/results_*.json  — per-model scoring results
    bench/meta/meta_<model>.json  — (optional) run metadata:
        {
          "model_file": "...",
          "context_size": 32768,
          "compactions": 3,
          "notes": "..."
        }
        Missing file -> those columns show "-".

Output:
    1) Summary table: file x benchmark (acc %) + OVERALL + Time.
    2) Per-model detail: correct/total, acc, per-test time, total time,
       context and compactions (when meta exists).

Both tables are FIXED_WIDTH=169 chars; long filenames/notes get an ellipsis.
"""
import json, os, glob

OUT = os.path.dirname(os.path.abspath(__file__))
BENCHES = ["MMLU", "GSM8K", "HellaSwag", "ARC-Chall", "MATH",
           "WinoGrande", "BBH", "HumanEval", "Terminal", "TermHard"]

FIXED_WIDTH = 169
FILE_W = 48
BENCH_W = 7
OVERALL_W = 8
TIME_W = 12
NOTE_W = 30
# FILE_W + BENCH_W*len(BENCHES) + OVERALL_W + TIME_W + NOTE_W + 1 (sep) == 169

# alias -> GGUF filename; fallback for runs whose meta lacks an auto-resolved model_file
MODEL_FILES = {}
_mp = os.path.join(OUT, "model_files.json")
if os.path.exists(_mp):
    with open(_mp) as _f:
        MODEL_FILES = json.load(_f)


def resolve_model(run_name):
    """Match run_name against known model aliases (longest first)."""
    for model in sorted(MODEL_FILES, key=len, reverse=True):
        if run_name == model or run_name.startswith(model + "_"):
            return model
    return run_name.partition("_")[0]

# short column labels (fit in BENCH_W)
SHORT = {
    "MMLU": "MMLU", "GSM8K": "GSM8K", "HellaSwag": "Hella",
    "ARC-Chall": "ARC", "MATH": "MATH", "WinoGrande": "Wino",
    "BBH": "BBH", "HumanEval": "HumEv", "Terminal": "Term",
    "TermHard": "TermH",
}


def trunc(s, w):
    if len(s) <= w:
        return s
    return s[:w - 1] + "…"


def load_results():
    rows = {}
    for fp in sorted(glob.glob(os.path.join(OUT, "results", "results_*.json"))):
        with open(fp) as f:
            d = json.load(f)
        rows[d["model"]] = d
    return rows


def load_meta(model):
    fp = os.path.join(OUT, "meta", f"meta_{model}.json")
    if os.path.exists(fp):
        with open(fp) as f:
            return json.load(f)
    return None


def fmt_time(t):
    """Time is always seconds — no rounding to minutes/hours."""
    if t is None:
        return "-"
    return f"{t:.1f}s"


def main():
    rows = load_results()
    if not rows:
        print("no results/results_*.json found")
        return

    # ---------- 1) summary table ----------
    title = "SUMMARY TABLE (seed=1234, identical sample)"
    print("=" * FIXED_WIDTH)
    print(title)
    print("=" * FIXED_WIDTH)

    hdr = f"{'file':<{FILE_W}s}"
    for b in BENCHES:
        hdr += f"{SHORT[b]:>{BENCH_W}s}"
    hdr += f"{'OVERALL':>{OVERALL_W}s}"
    hdr += f"{'Time':>{TIME_W}s}"
    hdr += f" {'Note':<{NOTE_W}s}"
    print(hdr)
    print("-" * FIXED_WIDTH)

    for run_name, d in rows.items():
        model = resolve_model(run_name)
        meta = load_meta(run_name) or {}
        fname = meta.get("model_file") or MODEL_FILES.get(model, model)
        row = f"{trunc(fname, FILE_W):<{FILE_W}s}"
        for b in BENCHES:
            v = d["per_benchmark"].get(b)
            row += f"{v['acc']:>{BENCH_W - 1}.1f}%" if v else f"{'-':>{BENCH_W}s}"
        row += f"{d['overall']['acc']:>{OVERALL_W - 1}.1f}%"
        t = sum(v.get("time_s", 0) for v in d["per_benchmark"].values() if v)
        row += f"{fmt_time(t):>{TIME_W}s}"
        note = meta.get("notes")
        row += f" {trunc(note, NOTE_W):<{NOTE_W}s}" if note else f" {'-':<{NOTE_W}s}"
        print(row)
    print()

    # ---------- 2) per-model detail ----------
    for run_name, d in rows.items():
        model = resolve_model(run_name)
        meta = load_meta(run_name)
        fname = (meta or {}).get("model_file") or MODEL_FILES.get(model, model)
        print("=" * FIXED_WIDTH)
        print(f"FILE: {fname}")
        print("=" * FIXED_WIDTH)

        b_w = max(len(b) for b in BENCHES) + 2
        c_w = len("correct") + 2
        t_w = len("total") + 2
        a_w = len("acc") + 2
        t2_w = max(len(fmt_time(v.get("time_s"))) for v in d["per_benchmark"].values() if v) + 2
        t2_w = max(t2_w, len("time") + 2)

        hdr = f"{'benchmark':<{b_w}s} {'correct':>{c_w}s} {'total':>{t_w}s} {'acc':>{a_w}s} {'time':>{t2_w}s}"
        print(hdr)
        print("-" * len(hdr))

        total_time = 0.0
        for b in BENCHES:
            v = d["per_benchmark"].get(b)
            if not v:
                continue
            t = v.get("time_s")
            if t is not None:
                total_time += t
            print(f"{b:<{b_w}s} {v['correct']:>{c_w}d} {v['total']:>{t_w}d} {v['acc']:>{a_w - 1}.1f}% {fmt_time(t):>{t2_w}s}")

        ov = d["overall"]
        print("-" * len(hdr))
        print(f"{'TOTAL':<{b_w}s} {ov['correct']:>{c_w}d} {ov['total']:>{t_w}d} {ov['acc']:>{a_w - 1}.1f}% {fmt_time(total_time):>{t2_w}s}")

        if meta:
            ctx = meta.get("context_size")
            comp = meta.get("compactions")
            print(f"  model context:   {ctx if ctx is not None else '-'} tokens")
            print(f"  compactions:     {comp if comp is not None else '-'}")
            if meta.get("notes"):
                print(f"  note:            {meta['notes']}")
        else:
            print(f"  model context:   - (no meta_{run_name}.json)")
            print(f"  compactions:     - (no meta_{run_name}.json)")
        print()


if __name__ == "__main__":
    main()
