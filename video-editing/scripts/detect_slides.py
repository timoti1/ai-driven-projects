#!/usr/bin/env python3
"""
detect_slides.py -- find slide/screen changes in a lecture screen recording.

Strategy: decode the video at a low fps into tiny grayscale thumbnails
(160x90), then flag frames whose mean-absolute-difference vs the previous
*stable* frame exceeds a threshold. Screen-recording slides produce large,
instant jumps; slow scrolling or cursor movement produces small ones.

A short hysteresis (min gap between changes) avoids double-triggering on
transition animation frames.

Usage:
  detect_slides.py VIDEO OUT.json [--fps 1] [--thr 18] [--min-gap 2.0]
"""
import argparse, json, subprocess, sys
import numpy as np


def run(src, fps, w, h):
    cmd = ["ffmpeg", "-v", "error", "-i", src, "-vf",
           f"fps={fps},scale={w}:{h}:flags=area,format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.exit("ffmpeg failed: " + p.stderr.decode()[-2000:])
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, h, w).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=160)
    ap.add_argument("--height", type=int, default=90)
    ap.add_argument("--thr", type=float, default=18.0,
                    help="mean abs diff (0-255) to call a change")
    ap.add_argument("--min-gap", type=float, default=2.0, help="sec between changes")
    a = ap.parse_args()

    frames = run(a.video, a.fps, a.width, a.height)
    dt = 1.0 / a.fps
    print(f"frames={len(frames)} ({len(frames)*dt:.0f}s)", file=sys.stderr)

    changes, prev, last_t = [], frames[0], -1e9
    for i in range(1, len(frames)):
        d = float(np.abs(frames[i] - prev).mean())
        t = i * dt
        if d > a.thr and (t - last_t) >= a.min_gap:
            changes.append({"t": round(t, 2), "diff": round(d, 2)})
            last_t = t
        # always track slowly so gradual drift does not accumulate into a
        # false "big change"; a real slide swap still trips the threshold
        prev = frames[i]

    # second pass: require the change to persist (new slide is stable), which
    # kills single-frame flicker from animations/cursor blinks
    stable = []
    idx = {c["t"]: int(round(c["t"] / dt)) for c in changes}
    for c in changes:
        i = idx[c["t"]]
        if i + 2 < len(frames):
            d_after = float(np.abs(frames[i + 2] - frames[i]).mean())
            if d_after < a.thr * 0.6:
                stable.append(c)
    if not stable and changes:
        stable = changes

    with open(a.out, "w") as fh:
        json.dump({"video": a.video, "fps": a.fps, "thr": a.thr,
                   "n_raw": len(changes), "n_stable": len(stable),
                   "changes": stable}, fh)
    print(f"changes raw={len(changes)} stable={len(stable)} -> {a.out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
