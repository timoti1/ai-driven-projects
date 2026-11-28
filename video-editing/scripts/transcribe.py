#!/usr/bin/env python3
"""
transcribe.py -- word-level transcript with faster-whisper, same output as parse_vtt.py.

PIPELINE.md prefers YouTube's (auto) captions: they are free, fast and already
word-timed.  This script is the fallback for a source with no captions at all.
It writes the identical JSON shape, so nothing downstream -- build_plan.py,
panel_gates.py, audit_titles.py -- can tell the difference:

    { "source": ..., "n_words": N, "duration": SECONDS,
      "words": [ { "t": SECONDS, "w": "word" }, ... ],
      "speech": "full text" }

`words[].t` is the time in the SOURCE file, so a WAV extracted from the video
must start at the video's zero (see ENVIRONMENT.md: extract with -vn, no trim).

Word timestamps come from the model's own alignment pass, which is what makes
them good enough to snap cuts to a pause (build_plan.py) and to audit topic
titles against what is actually said (audit_titles.py).  They are not exact:
expect a few hundred ms of drift on long words.

Usage:
  transcribe.py IN.wav OUT.json [--model large-v3] [--language ru]
                      [--device cpu] [--compute-type int8] [--beam 5]
                      [--gpu]

Speed: large-v3 on CPU is roughly 0.1x realtime (a 2 h lecture takes hours) --
that is why captions are preferred.  Add --gpu only when the GPU is free; on
this machine llama-server keeps it, so the default is CPU int8.
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", help="WAV (16 kHz mono is enough)")
    ap.add_argument("out")
    ap.add_argument("--model", default="large-v3",
                    help="faster-whisper model name or local dir (default large-v3; "
                         "small.en/tiny are faster and much worse on Russian)")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8",
                    help="int8 on CPU, float16 on GPU")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--gpu", action="store_true",
                    help="shortcut for --device cuda --compute-type float16")
    a = ap.parse_args()
    if a.gpu:
        a.device, a.compute_type = "cuda", "float16"

    # downloaded once into ~/.cache/huggingface, then reused offline
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    segments, info = model.transcribe(
        a.inp, language=a.language, word_timestamps=True,
        beam_size=a.beam, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=400))

    words, text = [], []
    n = 0
    for seg in segments:
        for w in seg.words or []:
            wd = w.word.strip()
            if not wd:
                continue
            words.append({"t": round(float(w.start), 3), "w": wd})
            text.append(wd)
            n += 1
            if n % 2000 == 0:
                print(f"  {n} words, up to {w.start:.0f} s", file=sys.stderr)
    duration = max([w["t"] for w in words], default=0.0)
    try:
        import soundfile as sf
        duration = max(duration, float(sf.info(a.inp).duration))
    except Exception:
        pass

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    json.dump({"source": os.path.abspath(a.inp), "n_words": n,
               "duration": round(duration, 3), "words": words,
               "speech": " ".join(text)},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{n} words, duration {duration:.2f}s, model {a.model} "
          f"({a.device}/{a.compute_type}) -> {a.out}")
    print("word timing is model-aligned: good enough to snap cuts and to audit "
          "titles, not good enough to cut on a single word boundary")


if __name__ == "__main__":
    main()
