#!/usr/bin/env python3
"""
analyze_motion.py -- how much the screen changes over time.

Decodes the whole video at --fps (default 2) into small grayscale thumbnails
and records the mean absolute difference between neighbouring frames. The
result answers one question for every moment of the lecture: *is the lecturer
drawing or scrolling right now?*

build_plan.py uses it to refuse a cut whose neighbourhood is not still, because
a jump in the middle of a hand-drawn diagram is plainly visible and the brief
says not to spoil the picture. On this recording the median frame difference is
0.00 (the screen is frozen while he talks) and only ~1 % of moments exceed 6,
so the filter is cheap and it does reject real cuts (17 of them here).

Writes:
  work/thumbs<fps>.npy   cached thumbnails (uint8)
  work/motion<fps>.npy   per-interval motion score (float32)
  work/motion_stats.json percentiles, for choosing --motion-max

Usage: analyze_motion.py VIDEO WORK_DIR [--fps 2] [--width 320] [--height 180]
"""
import argparse, json, os, subprocess, sys
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("workdir")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=180)
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)

    scale = f"fps={a.fps},scale={a.width}:{a.height}:flags=area,format=gray"
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", scale,
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        sys.exit("ffmpeg failed: " + p.stderr.decode()[-1500:])

    f = np.frombuffer(p.stdout, np.uint8).reshape(-1, a.height, a.width)
    d = np.abs(np.diff(f.astype(np.float32), axis=0)).mean(axis=(1, 2))

    tag = str(int(a.fps)) if float(a.fps).is_integer() else str(a.fps)
    np.save(os.path.join(a.workdir, f"thumbs{tag}fps.npy"), f)
    np.save(os.path.join(a.workdir, f"motion{tag}fps.npy"), d.astype(np.float32))

    q = lambda p: [round(float(v), 3) for v in np.percentile(d, p)]
    json.dump({
        "fps": a.fps, "frames": int(len(f)), "interval_seconds": 1.0 / a.fps,
        "motion_percentiles_p50_90_99": q([50, 90, 99]),
        "motion_max": round(float(d.max()), 2),
        "share_above_1_2": round(float((d > 1.2).mean()), 4),
        "share_above_6": round(float((d > 6).mean()), 4),
    }, open(os.path.join(a.workdir, "motion_stats.json"), "w"), indent=2)

    print(f"frames={len(f)} motion median={np.median(d):.3f} "
          f"p90={np.percentile(d,90):.2f} max={d.max():.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
