#!/usr/bin/env python3
"""Harvest messy Russian dictation prompts from pi session history."""
import json, os, re, glob

FILL = ["короче", "типа", "ну", "вот", "значит", "как бы", "это самое", "в общем",
        "то есть", "так сказать", "знаешь", "понимаешь", "блин", "допустим",
        "и так далее", "собственно", "реально", "честно", "что-то", "какой-то"]
RU = re.compile(r"[а-яё]", re.I)


def user_texts(root="~/.pi/agent/sessions"):
    for path in glob.glob(os.path.expanduser(root + "/**/*.jsonl"), recursive=True):
        try:
            with open(path) as f:
                for line in f:
                    if '"role":"user"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    m = d.get("message") or {}
                    if m.get("role") != "user":
                        continue
                    for c in (m.get("content") or []):
                        if isinstance(c, dict) and c.get("type") == "text":
                            t = c.get("text", "").strip()
                            if t:
                                yield t
        except Exception:
            pass


def score(t):
    """Higher = messier: filler density + immediate repeats + missing punctuation."""
    low = t.lower()
    words = re.findall(r"[а-яёa-z]+", low)
    n = len(words) or 1
    fill = sum(low.count(" " + w + " ") for w in FILL)
    rep = sum(1 for a, b in zip(words, words[1:]) if a == b and len(a) > 2)
    nopunct = 0 if re.search(r"[.!?]|\n", t) else 2
    return fill / n * 100 + rep * 4 + nopunct + (0 if "," in t else 1.5)


def main():
    seen, out = set(), []
    for t in user_texts():
        t = re.sub(r"<[^>]+>", " ", t)
        if not (60 <= len(t) <= 700) or t in seen:
            continue
        ru = len(RU.findall(t))
        if ru / max(len(t), 1) < 0.5:
            continue
        seen.add(t)
        out.append((score(t), t))
    out.sort(reverse=True)
    json.dump([t for _, t in out[:40]], open("/tmp/messy_prompts.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"{len(out)} unique Russian prompts; top messiness saved to /tmp/messy_prompts.json")


if __name__ == "__main__":
    main()
