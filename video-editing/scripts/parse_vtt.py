#!/usr/bin/env python3
"""
parse_vtt.py -- clean, word-level transcript from a YouTube VTT (incl. auto-CC).

YouTube auto captions are a *rolling window*: each cue repeats the previous
line and appends a new one, and every line is also emitted once as a "hold"
cue with no inline tags. Naive extraction therefore duplicates almost
everything. We undo that with the standard rolling-caption dedup:

  prev = ""
  for cue in cues:
      new = drop_longest_overlap(prev, cue.text)   # keep only the tail
      emit(new)                                     # timed by inline tags
      prev = cue.text

Inline `<00:00:01.020>` tags give per-word timing; cues without tags get
their words spread evenly across the cue window.

Usage:
  parse_vtt.py IN.vtt OUT.json [--gap-tol 0.35]
"""
import argparse, json, re, sys

TAG_RE = re.compile(r"<((?:\d+:)?\d{1,2}:\d{2}\.\d{3})>")
TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})")
WORD_RE = re.compile(r"[0-9A-Za-z\u0400-\u04FF'’-]+")


def ts(s):
    m = TS_RE.fullmatch(s.strip())
    if not m:
        return -1.0
    h, mi, se, ms = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + se + ms / 1000.0


def parse_cues(path):
    raw = open(path, encoding="utf-8-sig").read()
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2 or "-->" not in lines[0]:
            continue
        a = TS_RE.search(lines[0].split("-->")[0])
        b = TS_RE.search(lines[0].split("-->")[1])
        if not a or not b:
            continue
        start, end = ts(":".join(a.groups()[:3]) + "." + a.group(4)), \
                     ts(":".join(b.groups()[:3]) + "." + b.group(4))
        body = " ".join(lines[1:])
        body = re.sub(r"</?c>", " ", body)
        body = re.sub(r"\{[^}]*\}", "", body)          # vtt styling
        # keep inline timestamps in the joined body
        cues.append({"start": start, "end": end, "raw": " ".join(lines[1:]),
                     "text": re.sub(r"\s+", " ", body).strip()})
    cues.sort(key=lambda c: (c["start"], c["end"]))
    return cues


def words_from_raw(raw, cue_start, cue_end):
    """Word list from a cue body, using inline tags where present."""
    toks = re.split(r"(<(?:\d+:)?\d{1,2}:\d{2}\.\d{3}>)", raw)
    toks = [t for t in toks if t is not None]
    out, cur = [], cue_start
    seen_tag = False
    for t in toks:
        m = TAG_RE.fullmatch(t.strip()) if t.strip().startswith("<") else None
        if m:
            v = ts(m.group(1))
            if v >= 0:
                cur = v
                seen_tag = True
            continue
        t = re.sub(r"</?c>", " ", t)
        for w in WORD_RE.findall(t):
            out.append((cur, w))
    if not out:
        return []
    if not seen_tag:                       # no inline timing -> spread evenly
        span = max(cue_end - cue_start, 0.05) / max(len(out), 1)
        out = [(cue_start + i * span, w) for i, (_, w) in enumerate(out)]
    return out


def norm(w):
    return w.lower().strip(".,!?;:()\"'’")


def dedup_rolling(cues):
    """Return [(t, word)] with rolling repeats removed."""
    out, prev = [], []          # prev: list of normalized words of last cue
    for c in cues:
        ws = words_from_raw(c["raw"], c["start"], c["end"])
        if not ws:
            continue
        cur = [norm(w) for _, w in ws]
        # longest k such that tail(prev,k) == head(cur,k)
        k = 0
        for cand in range(min(len(prev), len(cur)), 0, -1):
            if prev[-cand:] == cur[:cand]:
                k = cand
                break
        new = ws[k:]
        out.extend(new)
        prev = cur
    return out


def speech_spans(words, gap_tol):
    if not words:
        return []
    spans, start, prev = [], words[0]["t"], words[0]["t"]
    for w in words[1:]:
        if w["t"] - prev > gap_tol:
            spans.append([round(start, 3), round(prev, 3)])
            start = w["t"]
        prev = w["t"]
    spans.append([round(start, 3), round(prev, 3)])
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vtt"); ap.add_argument("out")
    ap.add_argument("--gap-tol", type=float, default=0.30)
    a = ap.parse_args()

    cues = parse_cues(a.vtt)
    pairs = dedup_rolling(cues)
    pairs.sort(key=lambda x: x[0])
    words = [{"t": round(t, 3), "w": w} for t, w in pairs]
    spans = speech_spans(words, a.gap_tol)

    json.dump({"source": a.vtt, "n_cues": len(cues), "n_words": len(words),
               "duration": words[-1]["t"] if words else 0.0,
               "words": words, "speech": spans},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"cues={len(cues)} words={len(words)} spans={len(spans)} "
          f"last={words[-1]['t']:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
