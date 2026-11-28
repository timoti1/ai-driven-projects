#!/usr/bin/env python3
"""
Cut the lecture audio to the same timeline as the video, exactly.

Why not do this inside ffmpeg with aselect?  aselect works on *audio frames*,
which are fixed-size blocks of 1024 samples (23.2 ms at 44.1 kHz).  A kept
interval that starts on the 25 fps grid (a multiple of 40 ms) almost never
starts on an audio-block boundary, so the straddling block is dropped whole:
measured, precisely ~40 ms of audio disappears at every cut, which over 414
cuts means the narration arriving 16 s early by the end of the lecture.
Resampling first does not help, because aresample keeps the block sample
count, so the blocks still do not land on 40 ms.

So the audio is cut here, sample-exactly, and the result is handed to
render.py as a plain WAV that needs no cutting filter at all.  Blocks are
irrelevant because we slice a raw PCM stream by sample index.

The stream is copied block by block from ffmpeg's stdout, so peak memory is
one 1 MiB block regardless of lecture length (this host has ~8 GB free while
a model server holds the rest).

Usage:
    python scripts/cut_audio.py                  # writes render/audio_cut.wav
    python scripts/cut_audio.py --dry-run        # report only
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000          # output sample rate; 1 frame of 25 fps = 1920 samples here
CH = 2              # stereo; samples are interleaved, so cut on sample pairs


def load_kept():
    cuts = json.load(open(os.path.join(ROOT, "edit/cuts.json"), encoding="utf-8"))
    return cuts["kept"], cuts["edited_duration"]


def sample_ranges(kept):
    """Kept time intervals -> [start, end) sample indices at SR."""
    out = []
    for s, e in kept:
        a = int(round(s * SR))
        b = int(round(e * SR))
        if b > a:
            out.append([a, b])
    return out


def pcm_stream(src, block_samples=1 << 18):
    """Decode the source audio to interleaved s16le at SR, yielded as blocks."""
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", src, "-vn", "-acodec", "pcm_s16le",
         "-ac", str(CH), "-ar", str(SR), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    nbytes = block_samples * CH * 2
    while True:
        buf = p.stdout.read(nbytes)
        if not buf:
            break
        if len(buf) % (CH * 2):
            buf = buf[:len(buf) - len(buf) % (CH * 2)]
        yield np.frombuffer(buf, dtype="<i2").reshape(-1, CH)
    p.stdout.close()
    if p.wait():
        sys.exit("ffmpeg audio decode failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "render/audio_cut.wav"))
    a = ap.parse_args()

    kept, planned = load_kept()
    ranges = sample_ranges(kept)
    want = sum(b - s for s, b in ranges)
    print(f"{len(ranges)} kept ranges -> {want} samples = {want / SR:.3f}s "
          f"(plan says {planned:.3f}s)")

    src = os.path.join(ROOT, "source",
                       json.load(open(os.path.join(ROOT, "edit/topics.json"),
                                      encoding="utf-8"))["video_id"] + ".mp4")
    if not os.path.exists(src):
        sys.exit(f"missing {src}")

    # WAV header, rewritten at the end with the true length.  Offsets matter:
    # RIFF/size/WAVE at 0..11, "fmt " + 16-byte body at 12..35, "data" + size
    # at 36..43, samples from 44.
    hdr = bytearray(44)
    import struct
    hdr[0:4] = b"RIFF"
    hdr[8:12] = b"WAVE"
    hdr[12:16] = b"fmt "
    hdr[16:20] = struct.pack("<I", 16)
    hdr[20:36] = struct.pack("<HHIIHH", 1, CH, SR, SR * CH * 2, CH * 2, 16)
    hdr[36:40] = b"data"

    pos = 0          # samples consumed from the source
    written = 0
    ri = 0
    fh = open(os.devnull, "wb") if a.dry_run else open(a.out, "wb")
    fh.write(hdr)
    for block in pcm_stream(src):
        n = len(block)
        while ri < len(ranges):
            s, e = ranges[ri]
            lo, hi = max(s, pos), min(e, pos + n)
            if hi > lo:
                fh.write(block[lo - pos:hi - pos].tobytes())
                written += hi - lo
            if e <= pos + n:
                ri += 1
            else:
                break
        pos += n
        if ri >= len(ranges):
            break
    if not a.dry_run:
        hdr[4:8] = struct.pack("<I", 36 + written * CH * 2)
        hdr[40:44] = struct.pack("<I", written * CH * 2)
        fh.seek(0)
        fh.write(hdr)
    fh.close()
    print(f"wrote {written} samples = {written / SR:.3f}s "
          f"({written / want * 100:.3f}% of plan)"
          + ("" if a.dry_run else f" -> {a.out}"))
    if abs(written / SR - planned) > 0.001:
        print(f"WARNING: differs from plan by {written / SR - planned:+.3f}s")


if __name__ == "__main__":
    main()
