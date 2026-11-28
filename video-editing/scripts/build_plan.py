#!/usr/bin/env python3
"""
build_plan.py -- turn analysis results into an edit plan.

Inputs
  work/speech.json        word timeline + speech spans   (parse_vtt.py)
  work/silence_raw.txt    ffmpeg silencedetect stderr    (noise=-33dB:d=0.45)
  work/motion2fps.npy     per-0.5s screen-motion score   (cached thumbnails)
  edit/topics.json        topic map in SOURCE seconds

Outputs
  edit/cuts.json          kept intervals in source time + edited-time map
  edit/topics_edited.json topics in EDITED time (for the dashboard overlay)
  edit/stats.json         what the edit did, for the docs

Cut policy (why each rule exists)
  * we shorten long silences instead of deleting them: keeping a short
    breath at both edges preserves prosody and avoids a staccato feel
  * we only cut *inside* silence, never inside a word -> no clipped syllables
  * we skip a cut when the screen is being drawn on at that moment, because a
    jump in a hand-drawn diagram is visible and the brief says "don't spoil
    the picture"
  * filler words are cut only when they sit in their own silence pocket, so
    the cut lands on silence on both sides

Usage: build_plan.py [--over 0.85] [--keep-edge 0.15] [--motion-max 1.2]
"""
import argparse
import subprocess, json, math, os, re, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def parse_silences(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    st = [float(m.group(1)) for m in re.finditer(r"silence_start: ([\d.]+)", txt)]
    du = [float(m.group(1)) for m in re.finditer(r"silence_duration: ([\d.]+)", txt)]
    return [(s, s + d, d) for s, d in zip(st, du)]


def motion_at(motion, t0, t1, fps=2.0):
    a, b = int(t0 * fps), max(int(t1 * fps), int(t0 * fps) + 1)
    a = max(a, 0); b = min(b, len(motion))
    if b <= a:
        return 0.0
    return float(motion[a:b].mean())


# Only unambiguous hesitation tokens. "вот / это / так / значит" are ordinary
# content words in Russian and must never be auto-cut.
FILL_STRICT = {"э", "э-э", "ээ", "эээ", "эм", "м-м", "ы", "аа", "ну-у"}


def find_fillers(words, rms=None, dt=0.01, floor=-31.0):
    """
    Hesitation tokens that are (a) long on their own and (b) acoustically
    quiet, i.e. the token is a drawn-out breath rather than a spoken word.

    Note: YouTube auto-captions normally strip hesitations, so on this channel
    this returns nothing and filler handling falls back to audio denoising.
    """
    out = []
    for i, w in enumerate(words):
        norm = w["w"].lower().strip(".,!?;:-")
        if norm not in FILL_STRICT:
            continue
        nxt = words[i + 1]["t"] if i + 1 < len(words) else w["t"] + 0.5
        if nxt - w["t"] < 0.5:
            continue
        if rms is not None:
            a, b = int(w["t"] / dt), int(nxt / dt)
            if float(np.nanmax(rms[a:b])) > floor:
                continue          # it is loud -> real speech, do not cut
        out.append((w["t"], nxt, w["w"]))
    return out


def merge_intervals(xs, gap=0.05):
    if not xs:
        return []
    xs = sorted(xs)
    out = [list(xs[0])]
    for s, e in xs[1:]:
        if s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--over", type=float, default=0.70,
                    help="silences longer than this get shortened")
    ap.add_argument("--keep-edge", type=float, default=0.16,
                    help="seconds of silence kept at each edge of a short pause")
    ap.add_argument("--keep-long", type=float, default=0.10,
                    help="seconds kept at each edge of a long pause (> --long-above)")
    ap.add_argument("--long-above", type=float, default=1.30,
                    help="pause length that switches to the aggressive tier")
    ap.add_argument("--min-cut", type=float, default=0.12,
                    help="ignore cuts shorter than this")
    ap.add_argument("--motion-max", type=float, default=1.2,
                    help="skip cut if mean screen motion around it exceeds this")
    ap.add_argument("--edge-max-db", type=float, default=-30.0,
                    help="skip cut if audio at either splice edge is louder "
                         "than this (would clip a word)")
    ap.add_argument("--fillers", action="store_true", default=True)
    ap.add_argument("--no-fillers", dest="fillers", action="store_false")
    ap.add_argument("--fps", type=float, default=25.0,
                    help="source frame rate; kept intervals are snapped to this grid")
    ap.add_argument("--head-trim", type=float, default=1.2)
    ap.add_argument("--tail-pad", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=0.0,
                    help="source duration in seconds; defaults to the end of the "
                         "last topic in edit/topics.json")
    a = ap.parse_args()

    sp = load_json(os.path.join(ROOT, "work/speech.json"))
    topics = load_json(os.path.join(ROOT, "edit/topics.json"))
    vid = topics.get("video_id", "")
    sil = parse_silences(os.path.join(ROOT, "work/silence_raw.txt"))
    motion = np.load(os.path.join(ROOT, "work/motion2fps.npy"))
    rms_path = os.path.join(ROOT, "work/rms.npy")
    rms = np.load(rms_path) if os.path.exists(rms_path) else None
    # Source duration: never hardcode it, or the next episode silently keeps
    # the previous episode's length.  ffprobe asks the file, which cannot go
    # stale.  The last topic's "t" is its *start*, so it is only a fallback.
    dur = float(a.duration)
    for cand in (f"{vid}.mp4", "input.mp4", "lecture.mp4"):
        if dur or not os.path.exists(os.path.join(ROOT, "source", cand)):
            continue
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 os.path.join(ROOT, "source", cand)], text=True)
            dur = float(out.strip())
        except Exception:
            pass
    if not dur:
        dur = float(topics["topics"][-1]["t"]) if topics.get("topics") else 0.0
    if not dur:
        raise SystemExit("build_plan.py: cannot work out the source duration "
                         "(set video_id in edit/topics.json with source/<id>.mp4 "
                         "in place, or pass --duration)")

    removed, skipped_motion = [], []
    skipped_loud = []

    def edge_db(t):
        """Peak level in the 100 ms window ending/starting at t."""
        if rms is None:
            return -99.0
        i = int(t / 0.01)
        for lo, hi in ((i - 10, i), (i, i + 10)):
            lo, hi = max(lo, 0), min(hi, len(rms))
            if hi > lo and float(np.nanmax(rms[lo:hi])) > a.edge_max_db:
                return float(np.nanmax(rms[lo:hi]))
        return -99.0

    def edge_for(d):
        """Two tiers: a normal pause keeps a breath, a long dead-air pause is
        cut down much harder because that is where the lecture drags."""
        return a.keep_long if d > a.long_above else a.keep_edge

    removed, skipped_motion = [], []
    for s, e, d in sil:
        if d <= a.over:
            continue
        k = edge_for(d)
        cs, ce = s + k, e - k
        if ce - cs < a.min_cut:
            continue
        m = motion_at(motion, s - 0.6, e + 0.6)
        if m > a.motion_max:
            skipped_motion.append({"t": round(s, 2), "dur": round(d, 2),
                                   "motion": round(m, 2)})
            continue
        # the silence detector floor (-33 dB) is only ~5 dB below normal speech
        # level on this recording, so a "pause" can still contain the tail of a
        # quiet word; refuse the cut rather than clip a syllable
        lv = max(edge_db(cs), edge_db(ce))
        if lv > a.edge_max_db:
            skipped_loud.append({"t": round(s, 2), "dur": round(d, 2),
                                 "edge_db": round(lv, 1)})
            continue
        removed.append([cs, ce])

    filler_cuts = []
    if a.fillers:
        for s, e, w in find_fillers(sp["words"], rms):
            filler_cuts.append([s, e])
            removed.append([s, e])

    removed = merge_intervals(removed, gap=0.30)

    # invert -> kept intervals
    kept, cur = [], 0.0 + a.head_trim
    for s, e in removed:
        if s > cur:
            kept.append([round(cur, 3), round(s, 3)])
        cur = max(cur, e)
    if cur < dur - a.tail_pad:
        kept.append([round(cur, 3), round(dur - a.tail_pad, 3)])
    kept = [k for k in kept if k[1] - k[0] > 0.25]

    # Snap every kept interval onto the source frame grid. Two reasons:
    #  * select's between(t,s,e) is INCLUSIVE, so an off-grid range keeps a
    #    variable number of frames and the rendered length drifts from the plan
    #    (the first render came out 1.76 s / 44 frames longer than planned, so
    #    the dashboard clock never reached the total it prints);
    #  * on-grid bounds make edited_duration exactly frames/fps, so the plan,
    #    the dashboard timeline and the file all agree to the frame.
    fps = a.fps
    snapped = []
    for s, e in kept:
        s2 = math.ceil(s * fps - 1e-6) / fps
        e2 = math.floor(e * fps + 1e-6) / fps
        if e2 - s2 >= 1.0 / fps:
            snapped.append([round(s2, 6), round(e2, 6)])
    kept = snapped

    # source -> edited time mapping
    cum, acc = [], 0.0
    for s, e in kept:
        cum.append((s, e, acc))
        acc += e - s

    def to_edited(t):
        tot = 0.0
        for s, e, base in cum:
            if t <= s:
                break
            tot = base + min(t, e) - s
        return round(tot, 3)

    # snap topic boundaries onto real cut points so a topic never straddles
    # a mid-sentence splice
    bounds = sorted({round(k[1], 3) for k in kept} | {round(k[0], 3) for k in kept})
    snapped = []
    for tp in topics["topics"]:
        t = tp["t"]
        if t <= 0:
            snapped.append(0.0); continue
        cand = [b for b in bounds if abs(b - t) <= topics.get("snap", 30)]
        ns = min(cand, key=lambda b: abs(b - t)) if cand else t
        snapped.append(round(ns, 2))

    t_edit = []
    for i, tp in enumerate(topics["topics"]):
        s_e = to_edited(snapped[i])
        e_e = to_edited(snapped[i + 1]) if i + 1 < len(snapped) else round(acc, 3)
        t_edit.append({"i": i, "title": tp["title"], "short": tp["short"],
                       "recap": bool(tp.get("recap")),
                       "anchor": tp.get("anchor", ""),
                       "src_start": snapped[i],
                       "src_end": snapped[i + 1] if i + 1 < len(snapped) else dur,
                       "start": s_e, "end": e_e,
                       "dur_src": round((snapped[i + 1] if i + 1 < len(snapped)
                                         else dur) - snapped[i], 1),
                       "dur_edit": round(e_e - s_e, 1)})

    json.dump({"source_duration": dur, "kept": kept, "removed": removed,
               "n_cuts": len(kept) - 1, "edited_duration": round(acc, 3),
               "topic_bounds_src": snapped},
              open(os.path.join(ROOT, "edit/cuts.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    json.dump({"topics": t_edit, "edited_duration": round(acc, 3)},
              open(os.path.join(ROOT, "edit/topics_edited.json"), "w",
                   encoding="utf-8"), ensure_ascii=False)

    stats = {
        "source_duration": dur,
        "edited_duration": round(acc, 3),
        "removed_seconds": round(dur - acc, 1),
        "removed_pct": round(100 * (dur - acc) / dur, 2),
        "n_cuts": len(kept) - 1,
        "silences_total": len(sil),
        "silences_cut": len(removed) - len(filler_cuts),
        "fillers_cut": len(filler_cuts),
        "skipped_drawing": len(skipped_motion),
        "skipped_loud_edge": len(skipped_loud),
        "params": vars(a),
    }
    json.dump(stats, open(os.path.join(ROOT, "edit/stats.json"), "w"), indent=2)

    print(json.dumps(stats, indent=2))
    if skipped_motion:
        print(f"\nskipped {len(skipped_motion)} pauses (screen was being drawn on), "
              f"e.g. {skipped_motion[:5]}", file=sys.stderr)
    if skipped_loud:
        print(f"skipped {len(skipped_loud)} pauses (word tail at the splice), "
              f"e.g. {skipped_loud[:5]}", file=sys.stderr)


if __name__ == "__main__":
    main()
