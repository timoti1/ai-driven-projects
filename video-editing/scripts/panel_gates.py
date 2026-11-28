#!/usr/bin/env python3
"""
panel_gates.py -- decide when the dashboard may be drawn.

The dashboard lives in a column on the right edge, over what is *usually*
empty canvas margin. It is not empty for the whole lecture: measured on this
recording, between roughly 14:40 and 21:45 of the source the lecturer opens a
browser and a web page occupies exactly that column (up to 47% of its pixels),
and a couple of web pages appear later. Covering those with a 80%-opaque panel
would smother content the lecturer is showing.

So visibility is data-driven: measure per-frame how much ink sits under the
panel footprint, treat frames above a threshold as occupied, and emit time
ranges (in EDITED seconds) where the panel may be drawn.  render.py folds
those ranges into every dashboard filter's `enable` expression.

Occupancy is measured from work/thumbs2fps.npy (2 fps greyscale thumbnails
produced by analyze_motion.py), mapped through the kept intervals of
edit/cuts.json so the gates line up with the edited timeline.

  python scripts/panel_gates.py
  python scripts/panel_gates.py --ink-pct 1.5 --pad 1.0 --min-visible 6
"""
import argparse
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_panel_box():
    st = json.load(open(os.path.join(ROOT, "edit/style.json"), encoding="utf-8"))
    d = st.get("dashboard", {})
    return (d.get("panel_x", 1600), d.get("panel_w", 320),
            d.get("panel_y", 112), d.get("panel_h", 896))


def style_gates():
    """
    Gate thresholds from edit/style.json, so the dashboard's behaviour is tuned
    in the same file as its appearance.  Falls back to the values that produced
    the verified episode-1 gates when a key is absent.
    """
    d = {}
    try:
        st = json.load(open(os.path.join(ROOT, "edit/style.json"), encoding="utf-8"))
        d = st.get("dashboard", {})
    except (OSError, ValueError):
        pass
    return {
        "ink_pct": float(d.get("visible_ink_share", 0.015)) * 100.0,
        "pad": float(d.get("gate_pad_source", 1.0)),
        "merge": float(d.get("gate_merge_source", 4.0)),
        "min_visible": float(d.get("gate_min_visible_source", 6.0)),
        "min_hidden": float(d.get("gate_min_hidden_source", 2.0)),
    }



def merge(ranges, gap):
    """Merge [a,b] ranges that are within `gap` seconds of each other."""
    out = []
    for a, b in sorted(ranges):
        if out and a - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def complement(ranges, total):
    out, cur = [], 0.0
    for a, b in ranges:
        if a > cur:
            out.append([cur, min(a, total)])
        cur = max(cur, b)
    if cur < total:
        out.append([cur, total])
    return [[a, b] for a, b in out if b > a]


def main():
    g = style_gates()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ink-pct", type=float, default=g["ink_pct"],
                    help="hide the panel when more than this %% of its area is ink")
    ap.add_argument("--pad", type=float, default=g["pad"],
                    help="seconds added around each occupied stretch")
    ap.add_argument("--merge", type=float, default=g["merge"],
                    help="merge occupied stretches separated by less than this")
    ap.add_argument("--min-visible", type=float, default=g["min_visible"],
                    help="ignore clear stretches shorter than this (anti-flicker)")
    ap.add_argument("--min-hidden", type=float, default=g["min_hidden"],
                    help="ignore occupied stretches shorter than this")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "edit/panel_gates.json"))
    a = ap.parse_args()

    px, pw, py, ph = load_panel_box()
    th = np.load(os.path.join(ROOT, "work/thumbs2fps.npy")).astype(np.int16)
    N, H, W = th.shape
    sx, sy = W / 1920.0, H / 1080.0
    x0, x1 = int(px * sx), int((px + pw) * sx)
    y0, y1 = int(py * sy), int((py + ph) * sy)
    if x1 <= x0 + 1 or y1 <= y0 + 1:
        raise SystemExit("panel footprint smaller than one thumbnail pixel")

    cuts = json.load(open(os.path.join(ROOT, "edit/cuts.json"), encoding="utf-8"))
    kept = cuts["kept"]
    total = cuts["edited_duration"]

    # ink share of the panel footprint, per thumbnail frame (2 fps)
    frac = np.array([(th[i, y0:y1, x0:x1] < 110).mean() for i in range(N)])
    hot = np.where(frac * 100 > a.ink_pct)[0]
    occ_src = [[s / 2.0 - a.pad, (e + 1) / 2.0 + a.pad] for s, e in
               [(int(g[0]), int(g[-1])) for g in
                np.split(hot, np.where(np.diff(hot) > a.merge * 2)[0] + 1)]] if len(hot) else []
    occ_src = merge([(max(s, 0.0), min(e, cuts["source_duration"])) for s, e in occ_src], a.merge)

    # source time -> edited time, interval by interval
    occ_ed = []
    off = 0.0
    for ks, ke in kept:
        kd = ke - ks
        for os_, oe in occ_src:
            lo, hi = max(os_, ks), min(oe, ke)
            if hi > lo:
                occ_ed.append([off + (lo - ks), off + (hi - ks)])
        off += kd
    occ_ed = merge(occ_ed, 0.5)
    occ_ed = [[s, e] for s, e in occ_ed if e - s >= a.min_hidden]

    vis = [r for r in complement(occ_ed, total) if r[1] - r[0] >= a.min_visible]
    vis = merge(vis, 0.001)
    hid = complement(vis, total)

    hidden_s = sum(e - s for s, e in hid)
    json.dump({
        "_comment": [
            "When the dashboard may be drawn, in EDITED seconds.",
            "Generated by scripts/panel_gates.py from measured right-column",
            "occupancy; render.py multiplies these ranges into every",
            "dashboard filter's enable expression.",
            "Short stretches are swallowed so the panel never flickers.",
        ],
        "ink_pct": a.ink_pct, "pad": a.pad, "merge": a.merge,
        "min_visible": a.min_visible, "min_hidden": a.min_hidden,
        "edited_duration": total,
        "visible": [[round(s, 3), round(e, 3)] for s, e in vis],
        "hidden": [[round(s, 3), round(e, 3)] for s, e in hid],
    }, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"panel footprint x>={px} w={pw} y>={py} h={ph}")
    print(f"ink threshold {a.ink_pct}% -> {len(hot)} of {N} frames occupied "
          f"({hot.size / N * 100:.2f}%)")
    print(f"{len(vis)} visible / {len(hid)} hidden range(s); "
          f"panel hidden {hidden_s:.1f}s of {total:.1f}s "
          f"({hidden_s / total * 100:.2f}%) -> {a.out}")
    for s, e in hid:
        print(f"   hidden {s:8.1f}..{e:8.1f}  ({e - s:6.1f}s)")


if __name__ == "__main__":
    main()
