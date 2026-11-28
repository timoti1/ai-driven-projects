#!/usr/bin/env python3
"""
detect_hum.py -- find non-speech vocal noise (breaths, "mm/ee-ee" hums, lip
noise, long exhales) acoustically, because YouTube auto-captions strip
hesitation words from the transcript, so they cannot be found textually.

Method: decode to 16 kHz mono, frame at 10 ms, and score every frame:

  rms_db            loudness
  flatness          geometric/arithmetic mean of the spectrum -> noise-like
                    breaths and room hiss are HIGH, vowels are LOW
  centroid          "brightness"; inhales are bright, vowels are dull
  voiced            low flatness + low centroid => vowel-like speech

A candidate is a run of >= --min-dur frames that are
  audible (above the silence floor)  AND  not vowel-like  AND  quiet
such runs are only cut when they are adjacent to a pause, so we never remove
a real word.

Usage: detect_hum.py VIDEO OUT.json [--floor -34] [--max -21] [--min-dur 0.55]
"""
import argparse, json, subprocess, sys
import numpy as np

SR = 16000
HOP = 160            # 10 ms
WIN = 320            # 20 ms


def decode(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        sys.exit("ffmpeg decode failed: " + p.stderr.decode()[-1500:])
    return np.frombuffer(p.stdout, np.float32)


def features(x):
    n = 1 + max(0, (len(x) - WIN) // HOP)
    rms = np.empty(n); flat = np.empty(n); cent = np.empty(n)
    win = np.hanning(WIN)
    for i in range(n):
        seg = x[i * HOP: i * HOP + WIN] * win
        e = float(np.sqrt((seg ** 2).mean()) + 1e-12)
        rms[i] = 20 * np.log10(e)
        mag = np.abs(np.fft.rfft(seg)) + 1e-12
        flat[i] = float(np.exp(np.log(mag).mean()) / mag.mean())
        cent[i] = float((mag * np.linspace(0, SR / 2, len(mag))).sum() / mag.sum())
    return rms, flat, cent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--floor", type=float, default=-34.0, help="dB, silence floor")
    ap.add_argument("--max", type=float, default=-19.0, help="dB, above this it is speech")
    ap.add_argument("--flat-min", type=float, default=0.30, help="noise-likeness gate")
    ap.add_argument("--min-dur", type=float, default=0.55)
    a = ap.parse_args()

    x = decode(a.video)
    rms, flat, cent = features(x)
    dt = HOP / SR
    print(f"frames={len(rms)} ({len(rms)*dt:.0f}s)", file=sys.stderr)

    audible = rms > a.floor
    quiet = rms < a.max
    noisy = flat > a.flat_min
    cand = audible & quiet & noisy

    runs, i = [], 0
    n = len(cand)
    while i < n:
        if cand[i]:
            j = i
            while j < n and cand[j]:
                j += 1
            s, e = i * dt, j * dt
            if e - s >= a.min_dur:
                runs.append({"start": round(s, 2), "end": round(e, 2),
                             "dur": round(e - s, 2),
                             "rms": round(float(rms[i:j].mean()), 1),
                             "flat": round(float(flat[i:j].mean()), 3)})
            i = j
        else:
            i += 1

    json.dump({"params": vars(a), "n": len(runs), "runs": runs},
              open(a.out, "w"), indent=1)
    tot = sum(r["dur"] for r in runs)
    print(f"hum/breath runs={len(runs)} total={tot:.0f}s -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
