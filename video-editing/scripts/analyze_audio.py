#!/usr/bin/env python3
"""
analyze_audio.py -- per-frame loudness and spectral shape of the soundtrack.

Writes, into the given work directory:

  rms.npy    one float32 per 10 ms frame: level in dB
  flat.npy   spectral flatness (geometric mean / arithmetic mean of |FFT|)
  audio_stats.json   calibration numbers used to choose cut thresholds

Why these two features
  rms   silencedetect gives pause boundaries but not the level *at* a splice
        edge; build_plan.py refuses a cut whose edges are loud, which needs a
        per-frame level curve.
  flat  distinguishes noise-like sound (breath, hiss: high flatness) from
        vowel-like sound (low flatness). Measured on this recording the two
        distributions overlap far too much to cut fillers safely:

          speech  p10/p50/p90 rms = -42.3 / -28.3 / -19.7 dB
          silence p10/p50/p90 rms = -145.4 / -71.9 / -45.7 dB
          flat > 0.30 in speech 30.2 %, in silence 75.7 %

        i.e. normal quiet speech sits only ~5 dB above the silence floor, so
        "audible and noise-like" is not a reliable filler detector here. That
        is the documented reason filler words are handled by denoising rather
        than by cutting.

Usage: analyze_audio.py VIDEO WORK_DIR
"""
import argparse, json, os, subprocess, sys
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
    frames = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP][:n]
    rms = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-12)
    mag = np.abs(np.fft.rfft(frames * np.hanning(WIN))) + 1e-9
    flat = np.exp(np.log(mag).mean(axis=1)) / mag.mean(axis=1)
    cent = (mag * np.linspace(0, SR / 2, mag.shape[1])).sum(axis=1) / mag.sum(axis=1)
    return rms.astype(np.float32), flat.astype(np.float32), cent.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("workdir")
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)

    x = decode(a.video)
    rms, flat, cent = features(x)
    dt = HOP / SR
    np.save(os.path.join(a.workdir, "rms.npy"), rms)
    np.save(os.path.join(a.workdir, "flat.npy"), flat)

    q = lambda arr, p: [round(float(v), 3) for v in np.percentile(arr, p)]
    json.dump({
        "frames": int(len(rms)), "frame_seconds": dt,
        "rms_percentiles_p1_5_25_50_75_95_99": q(rms, [1, 5, 25, 50, 75, 95, 99]),
        "flat_percentiles_p1_5_25_50_75_95_99": q(flat, [1, 5, 25, 50, 75, 95, 99]),
        "centroid_hz_median": round(float(np.median(cent)), 1),
        "note": "speech sits only ~5 dB above the silence floor on this "
                "recording; see docs/EDIT_DECISIONS.md for why fillers were "
                "denoised instead of cut",
    }, open(os.path.join(a.workdir, "audio_stats.json"), "w"), indent=2)

    print(f"frames={len(rms)} ({len(rms)*dt:.0f}s) rms median={np.median(rms):.1f} dB "
          f"flat median={np.median(flat):.3f}", file=sys.stderr)


if __name__ == "__main__":
    main()
