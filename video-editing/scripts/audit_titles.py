#!/usr/bin/env python3
"""
audit_titles.py -- check that every topic name uses words the lecturer says.

The rule this enforces (docs/DECISIONS.md, edit/topics.json/_comment): a topic
is named from what is *said inside its own window*, never from what the lecture
is about in general.  Invented names cost real corrections: "Пруд vs океан"
became "Лейк и оушен" because the speaker says "лейк"/"оушен" (auto-captions
write them as "озерцо"/"океанов"), and "Кривая усилий: от хаоса к порядку"
named a window where neither "кривая усилий" nor "хаос" is ever uttered.

Rows may be named with the *field's* vocabulary rather than the lecturer's words
("Data Lake", "Аналогии, объясняющие ETL", "Выводы") -- that is what makes the
panel a table of contents instead of a transcript.  Such a row carries an
"anchor": a word that really is spoken inside its window, and the anchor is the
hard check.  Without an anchor the old strict rule applies.

Matching is by lemma, not by string: Russian inflects, so "токены" has to match
a spoken "токенами" and "слоям" a spoken "слой".  pymorphy3 does that; without it
the script falls back to five-letter prefix matching, which is looser but still
catches invented names.  Words that are not in the window but appear elsewhere in
the transcript are reported as warnings, not failures: the lecture does refer back.

--suggest also prints the most frequent substantive words of each failing
window, which is what a rename has to be built from.

Usage: audit_titles.py [topics.json] [speech.json] [--suggest]
Exit code 1 if some name is not spoken anywhere in its window.
"""
import json, os, re, sys

try:
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:
    _MORPH = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Words that carry no topical claim and are therefore not checked.
STOP = set("""и в на с для от к о как что это не по из за про or vs a то он она
мы вы они их его её ты вы же бы был была были будет есть надо если но так вот
какой какая какие самый самая общий общая всего всего только уже ещё еще""".split())

MIN_LEN = 5  # shorter tokens (S1, ETL, regex, БД) are names/symbols, not claims


# Auto-captions spell some Russian words with Latin look-alikes ("cлoи",
# "Сотriming"); a token that mixes scripts is folded to Cyrillic before it is
# looked up, otherwise a spoken word looks absent from its own window.
_PAIRS = [("a", "а"), ("c", "с"), ("e", "е"), ("o", "о"), ("p", "р"), ("x", "х"),
          ("y", "у"), ("k", "к"), ("A", "А"), ("B", "В"), ("C", "С"), ("E", "Е"),
          ("H", "Н"), ("K", "К"), ("M", "М"), ("N", "Н"), ("P", "Р"), ("T", "Т"),
          ("X", "Х"), ("Y", "У")]
LOOKALIKE = str.maketrans(dict(_PAIRS))


def norm(w):
    w = w.lower()
    if re.search(r"[а-яё]", w):  # mixed-script artifact, not a Latin term
        w = w.translate(LOOKALIKE)
    return re.sub(r"[^a-zа-яё0-9]+", "", w)


def stem(w):
    """Canonical key for a word: its lemma when a morph analyzer is available."""
    n = norm(w)
    if not n:
        return ""
    if _MORPH is not None:
        try:
            return _MORPH.parse(n)[0].normal_form
        except Exception:
            pass
    return n[:MIN_LEN]


def stems(words):
    return {stem(w) for w in words if len(norm(w)) >= MIN_LEN}


def flagged(text, spoken, anywhere, ok_stems):
    bad, warn = [], []
    text = text.replace("…", " ")
    for tok in re.split(r"[^\w]+", text):
        n = norm(tok)
        if not n or n in STOP or len(n) < MIN_LEN:
            continue
        if tok + "." in text:  # deliberately truncated panel label, e.g. "Структ."
            continue
        s = stem(tok)
        if s in spoken:
            continue
        if s in ok_stems:
            continue
        if s in anywhere:
            warn.append(tok)
        else:
            bad.append(tok)
    return bad, warn


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tpath = args[0] if args else os.path.join(ROOT, "edit/topics.json")
    spath = args[1] if len(args) > 1 else os.path.join(ROOT, "work/speech.json")
    top = json.load(open(tpath, encoding="utf-8"))
    sp = json.load(open(spath, encoding="utf-8"))
    words = sp["words"]
    dur = float(sp.get("duration", max(w["t"] for w in words) + 1))
    # lemma the whole transcript once: 30k words takes a few seconds, and every
    # window query then costs nothing.
    lexed = [(float(w["t"]), stem(w["w"])) for w in words]
    anywhere = {s for _, s in lexed if len(norm(s)) >= MIN_LEN or _MORPH}
    ok = stems(top.get("vocabulary_ok", []))
    print(f"  matcher: {'pymorphy3 lemmas' if _MORPH else 'five-letter prefixes'}")
    topics = top["topics"]

    suggest = "--suggest" in sys.argv
    fails = 0
    print(f"audit of {len(topics)} topic names against {len(words)} transcript words\n")
    for i, t in enumerate(topics):
        a = float(t["t"])
        b = float(topics[i + 1]["t"]) if i + 1 < len(topics) else dur
        # topic starts are snapped to speech gaps by up to `snap` seconds, so
        # the window is padded; a word just outside the nominal start still
        # belongs to the topic.
        pad = float(top.get("snap", 30))
        win = {s for t0, s in lexed if a - pad <= t0 < b + pad}
        bad, warn = flagged(f"{t['title']} {t['short']}", win, anywhere, ok)
        # A row may be named with the field's vocabulary rather than the
        # lecturer's ("Аналогии, объясняющие ETL", "Data Lake", "Выводы") -- that
        # is what makes the panel a table of contents instead of a transcript.
        # What keeps such a name honest is its `anchor`: a word that really is
        # spoken inside the window.  With an anchor, unsaid title words are
        # notes; without one, they are failures.
        anchor = t.get("anchor")
        astem = stem(anchor) if anchor else ""
        anchor_ok = bool(anchor) and (astem in win or
                                      any(v.startswith(astem[:MIN_LEN]) or
                                          astem.startswith(v[:MIN_LEN]) for v in win))
        if anchor:
            bad, warn = [], bad + warn
        title = "  ".join([t["title"], t["short"]])
        if anchor:
            title += f"   [anchor: {anchor}{'  ok' if anchor_ok else '  MISSING'}]"
        mark = "ok " if not bad and not warn else ("FAIL" if bad else "note")
        if anchor and not anchor_ok:
            mark = "FAIL"
        print(f"  {mark} {i:2d} [{a:6.0f}-{b:6.0f}] {title}")
        if anchor and not anchor_ok:
            fails += 1
            print(f"       anchor {anchor!r} (lemma {astem!r}) is not spoken in this window")
            if suggest:
                freq = {}
                for t0, lm in lexed:
                    if a - pad <= t0 < b + pad and len(lm) >= MIN_LEN and lm not in STOP:
                        freq[lm] = freq.get(lm, 0) + 1
                hot = sorted(freq.items(), key=lambda kv: -kv[1])[:14]
                print(f"       said there: {', '.join(f'{w}({n})' for w, n in hot)}")
        if bad:
            fails += 1
            print(f"       never said in this window (nor anywhere): {sorted(set(bad))}")
            if suggest:
                freq = {}
                for t0, lm in lexed:
                    if a - pad <= t0 < b + pad and len(lm) >= MIN_LEN and lm not in STOP:
                        freq[lm] = freq.get(lm, 0) + 1
                hot = sorted(freq.items(), key=lambda kv: -kv[1])[:14]
                print(f"       said there: {', '.join(f'{w}({n})' for w, n in hot)}")
        if warn:
            print(f"       not spoken in this window: {sorted(set(warn))}"
                  + ("  (name is field vocabulary; anchor carries the row)" if anchor else ""))
        if len(t["title"]) > 34 or len(t["short"]) > 20:
            print(f"       long for the layout: title {len(t['title'])} chars, "
                  f"short {len(t['short'])} chars (measured fit is what actually matters)")
    print()
    if fails:
        print(f"FAIL: {fails} topic row(s) are not backed by their window "
              f"(missing anchor, or an invented claim with no anchor to support it)")
        sys.exit(1)
    print("ok: every row's anchor is spoken in its own window")


if __name__ == "__main__":
    main()
