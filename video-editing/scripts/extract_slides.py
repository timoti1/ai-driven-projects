#!/usr/bin/env python3
"""
extract_slides.py -- pick one representative frame per stable screen and OCR it.

A lecture screen recording sits on one screen for a long time, then jumps.
We find those "stable runs" from 1 fps grayscale thumbnails (a run ends when
the frame differs from the run's reference by more than --thr), keep runs
longer than --min-hold seconds, grab the full-resolution frame from the middle
of each run, and OCR it with tesseract.

Output JSON:
  {"slides": [{"t": sec, "hold": sec, "frame": path, "text": "..."}]}

Usage:
  extract_slides.py VIDEO OUT_JSON [--thr 4] [--min-hold 25] [--lang rus+eng]
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np


def thumbs(src, fps=1.0, w=160, h=90):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf",
                        f"fps={fps},scale={w}:{h}:flags=area,format=gray",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        sys.exit("ffmpeg thumbs failed: " + p.stderr.decode()[-1500:])
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w).astype(np.float32)


def stable_runs(f, thr, dt, min_hold):
    """Return [(start_idx, end_idx)] of runs whose frames stay within thr of ref."""
    runs, i, n = [], 0, len(f)
    while i < n:
        ref = f[i]
        j = i + 1
        while j < n and float(np.abs(f[j] - ref).mean()) < thr:
            j += 1
        if (j - i) * dt >= min_hold:
            runs.append((i, j - 1))
        i = max(j, i + 1)
    return runs


def grab_frame(src, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src,
                    "-frames:v", "1", "-q:v", "2", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ocr(img, lang):
    p = subprocess.run(["tesseract", img, "stdout", "-l", lang,
                        "--psm", "6"], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    txt = p.stdout.decode("utf-8", "replace")
    txt = "\n".join(l.strip() for l in txt.splitlines() if l.strip())
    return txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--thr", type=float, default=4.0)
    ap.add_argument("--min-hold", type=float, default=25.0)
    ap.add_argument("--lang", default="rus+eng")
    ap.add_argument("--frames-dir", default=None)
    ap.add_argument("--max-slides", type=int, default=400)
    a = ap.parse_args()

    fdir = a.frames_dir or os.path.join(os.path.dirname(a.out) or ".", "slide_frames")
    os.makedirs(fdir, exist_ok=True)

    f = thumbs(a.video)
    dt = 1.0
    runs = stable_runs(f, a.thr, dt, a.min_hold)
    print(f"stable runs: {len(runs)}", file=sys.stderr)

    slides = []
    for k, (i, j) in enumerate(runs[:a.max_slides]):
        t = (i + j) / 2.0
        img = os.path.join(fdir, f"slide_{k:03d}_{int(t)}.jpg")
        if not os.path.exists(img):
            grab_frame(a.video, t, img)
        txt = ocr(img, a.lang) if os.path.exists(img) else ""
        slides.append({"t": round(t, 1), "start": round(i * dt, 1),
                       "end": round((j + 1) * dt, 1), "hold": round((j - i + 1) * dt, 1),
                       "frame": img, "text": txt})
        print(f"  slide {k:3d} t={t:7.1f} hold={slides[-1]['hold']:6.1f} "
              f"chars={len(txt):4d}", file=sys.stderr)

    json.dump({"video": a.video, "slides": slides},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"wrote {len(slides)} slides -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
