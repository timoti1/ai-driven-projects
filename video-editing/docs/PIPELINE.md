# Pipeline

Every step, in order, with the command to run.  Scripts live in `scripts/`,
what they read is in `source/` and `work/`, what they decide is in `edit/`,
what they render is in `render/`.

```
source/  ->  work/  ->  edit/  ->  render/
download     analysis    decisions   ffmpeg output
```

Reference numbers are from the first episode: 1 h 49 min lecture, 1920x1080
25 fps, Russian auto-captions, Ryzen 7 5800 (16 threads), AMD RX 9070 for
encoding.  They are there so a rerun can be sanity-checked.

---

## 0. Prepare (once)

```bash
cd /media/timoti/Storage/Work/vidproj
python3 -m venv .venv
.venv/bin/pip install yt-dlp faster-whisper pillow numpy pymorphy3 fonttools
sudo apt install -y ffmpeg tesseract-ocr tesseract-ocr-rus
mkdir -p logs source work work/audio work/frames work/slide_frames edit render
```

Versions, GPU choice and what each dependency is for: `ENVIRONMENT.md`.
`scripts/gpu_free.py` says whether an encoder card is idle.

---

## 1. Download the source

```bash
.venv/bin/yt-dlp -f "best-video+best-audio" --write-subs --write-auto-subs \
    --sub-langs "ru,*.ru" --write-info-json --write-thumbnail \
    -o "source/%(id)s.%(ext)s" "https://www.youtube.com/watch?v=VIDEO_ID"
```

Produces `source/<id>.mp4`, `source/<id>.info.json`, `source/<id>.<lang>.vtt`
(uploader captions if present, otherwise YouTube's auto-generated ones) and the
thumbnail.  The rest of the pipeline finds the video through
`video_id` in `edit/topics.json` → `source/<video_id>.mp4`, so no renaming is
needed.

If YouTube has **no** captions at all, transcribe instead (slower, and word
timing is worse than auto-CC):

```bash
ffmpeg -i source/<id>.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le source/<id>.wav
.venv/bin/python scripts/transcribe.py source/<id>.wav work/speech.json
```

**Check:** `ffprobe -v error -show_entries format=duration source/<id>.mp4`
agrees with `duration` in `source/<id>.info.json`.

---

## 2. Transcript: clean word-level timings

```bash
.venv/bin/python scripts/parse_vtt.py source/<id>.ru.vtt work/speech.json
```

YouTube auto-CC arrives as rolling karaoke captions: every block repeats the
previous block and adds a few words.  Concatenating naively duplicates most of
the lecture; deduplicating on exact text drops genuine repeats ("базы данных"
said twice in a row is two mentions).  `parse_vtt.py` aligns each block against
the previous one, keeps only what is new, and keeps one timestamp per word.
`--gap-tol` (default 0.35 s) decides how far apart two identical words have to
be to count as two utterances.

Output `work/speech.json`:

```json
{"source": "...vtt", "n_cues": 8310, "n_words": 12478, "duration": 6577.03,
 "words": [{"t": 45.26, "w": "Добрый"}, ...],
 "speech": [[45.26, 47.10], ...]}
```

`words` is what later steps trust for *what is said where*.  `speech` is merged
spans (a gap longer than `--gap-tol` ends a span) and is what stops a cut from
eating a word.

**Check:** words ÷ runtime should be plausible for the language (4–6 w/s for
Russian, slides included).  Double that means dedup failed; near zero means the
VTT is a different language.  Episode 1: 12478 words, first word at 45.26 s (the
lecture opens on a silent title card), last word ends at 6570.14 s.

---

## 3. Silence map (raw, untrimmed)

```bash
ffmpeg -i source/<id>.mp4 -vn -af "silencedetect=noise=-35dB:d=0.17" \
    -f null - 2> work/silence_raw.txt
```

About 30 s, audio only.  `build_plan.py` reads that exact filename.  This is
*raw* silence — no speech protection yet, the arbitration happens in step 8.
`-35 dB` / `d=0.17` suit a lecture peaking near −15 dB; episode 1 measured a
silence median of −57 dB and a speech floor of −37.6 dB.

---

## 4. Loudness and spectral shape

```bash
.venv/bin/python scripts/analyze_audio.py source/<id>.mp4 work
```

Writes `work/rms.npy` (dB per 10 ms frame), `work/flat.npy` (spectral flatness:
voiced vs click/air) and `work/audio_stats.json` (the calibration numbers).
The number that matters is the **speech floor** — the level speech stays above
— because it is what makes a proposed cut provably inside real silence.
Episode 1: −37.6 dB floor against a −57.1 dB silence median, a 20 dB margin.

---

## 5. Non-speech vocal noise (breaths, hums, smacks)

```bash
.venv/bin/python scripts/detect_hum.py source/<id>.mp4 work/hum.json
```

YouTube auto-CC *deletes* hesitation words, so "э-э", breaths and long exhales
are invisible to anything transcript-based.  They have to be found acoustically.
`detect_hum.py` scores windows by how voice-like and how *unlike* speech they
are: low flatness (voiced, not a click), loudness near the speech floor, long
flat envelope (an exhale), high zero-crossing rate (no pitch), short (not a
word).  In episode 1 the candidates grouped into one long breath region, and
`build_plan.py` only cuts silent parts inside it, so a breath is never cut in a
way that clips a word.

Its precision is deliberately poor — a quiet moment between slides looks like a
sigh — which is exactly why it is advisory and always intersected with silence.

---

## 6. Screen changes and motion

```bash
.venv/bin/python scripts/detect_slides.py source/<id>.mp4 work/screens.json --fps 4 --thr 18
.venv/bin/python scripts/analyze_motion.py source/<id>.mp4 work
```

`detect_slides.py` decodes at 4 fps and records where the frame differs from
the previous one by more than `--thr`; the stable ranges between changes are
screens.

`analyze_motion.py` writes two 2 fps arrays:

- `work/motion2fps.npy` — how much the picture changed between sampled frames.
  Keeps cuts out of the middle of a drawing animation and stops a cut from
  *skipping* the moment a drawing was finished (the viewer would see content
  appear out of nowhere).
- `work/thumbs2fps.npy` — 48x27 RGB thumbnails, 725 MB for a 1 h 49 min video.
  These feed the dashboard visibility gates and the slide OCR pick.  Reading it
  is the slowest part of the analysis (~4 min).

---

## 7. Slide OCR — what the screen says, and when

```bash
.venv/bin/python scripts/extract_slides.py source/<id>.mp4 work/slides.json --thr 4 --min-hold 25
```

Picks a representative frame per stable screen, scales it 2x, OCRs it
(rus+eng) and stores `{"slides":[{"t","start","hold","frame","text"}, ...]}`.
`--thr` here is a *stability* threshold (how different two frames of the same
screen may be), not the change threshold from step 6.

This is how a topic title gets anchored to a real slide: "БД и объёмы" is
verified against the slide that says "Уровень 2: корпоративная БД".  The first
line of each slide is also the lecture's own table of contents, which is the
fastest way to build the topic map in step 8.

---

## 8. Topic map — you decide, the script verifies

Write `edit/topics.json`:

```json
{"video_id": "F6fCcoNNdEE", "channel": "LearnToCode",
 "lesson": "Урок 1 · Введение", "title": "Теоретическая часть - 01. ...",
 "group": "Основы", "snap": 30,
 "vocabulary_ok": ["Data", "Lake", "ETL", "Spark", "Power", "BI", "regex"],
 "topics": [
   {"t": 0.0,    "title": "Введение: данные и их структура", "short": "Введение",
    "anchor": "структура", "recap": false},
   {"t": 150.0,  "title": "Структурированные данные",         "short": "Структ. данные",
    "anchor": "таблица", "recap": true},
   {"t": 630.0,  "title": "Data Lake: озеро против океана",   "short": "Data Lake",
    "anchor": "океан", "recap": true}
 ]}
```

- **How to name a topic** (DECISIONS 9).  The panel is a table of contents in the
  field's vocabulary, not a transcript of the example on screen:
  - name the **concept**, not the illustration: «Перегородки валюты» →
    «Аналогии, объясняющие ETL»; «картинки, аудио» → «Неструктурированные данные»;
    a row where a diagram is drawn is «Диаграмма: этапы и объём работ».
  - industry terms stay in English, never translated or transliterated: `Data
    Lake`, `ETL`, `Spark`, `Power BI` — not «Дейта Лейк» and not «Пруд vs океан».
  - generalise instead of quoting: the row is what a lecturer would write in an
    outline («Выводы», not «итог последнего слайда»).
  - every row needs an **`anchor`**: a word actually spoken inside its window.
    `audit_titles.py` fails the run when the anchor is missing; with an anchor, a
    title word that is not spoken («Аналогии», «Инструменты») is only a note.
    Without an anchor the strict rule applies, so a general name cannot be a guess.
- `t` is **source-video seconds** (not edited seconds); the dashboard's edited
  timeline is derived from `edit/cuts.json` by `build_plan.py`.
- `short` is what appears in the dashboard row; it is measured and
  shrunk/wrapped automatically, but a 40-word `short` is unreadable whatever
  the renderer does — keep them under ~20 characters.
- `title` is the full phrase for the outro recap.
- `"recap": true` marks the topics the outro card lists (9 in this episode, spread
  over it; the card shrinks its font to fit, so 6-12 is safe).  The flag lives on the topic, not as an index list in
  `style.json` — an index list shifts when a topic is added or removed, and
  `render.py` used to drop out-of-range indices without complaining
  (GOTCHAS #32).  If no topic is marked, the render stops with an error instead of
  printing a short card.
- `snap` is how far a topic boundary may be moved onto a nearby cut boundary
  when the two are that close.
- The source duration is not stored here: scripts ffprobe `source/<id>.mp4`.

Titles must come from the lecture, not from your summary of it — words the
lecturer actually said or a slide actually shows.  Fabricated titles ("БД vs
ТВ", "Трансформация данных в нужном формате") read as spoiling and as lying:
the row promises something the minute does not contain.  This is checked by a
script, not by eye:

```bash
.venv/bin/python scripts/audit_titles.py            # exit 1 if a name is invented
.venv/bin/python scripts/audit_titles.py --suggest  # and what that window does say
```

`audit_titles.py` lemmatises each topic window with pymorphy3 and fails if a
name uses a word the lecturer does not say there; words that appear elsewhere in
the transcript are reported as notes (the lecture does refer back).  Exceptions
are declared in `topics.json` under `vocabulary_ok` — brand spellings, and words
the speaker says in English while auto-captions write a Russian near-synonym.
`--suggest` prints the most frequent substantive words of every failing window,
which is what a rename has to be built from.

Episode 1 needed this: 10 of its 22 names were invented ("Пруд vs океан" where
he says лейк/оушен, "Кривая усилий: от хаоса к порядку" where neither "кривая
усилий" nor "хаос" occurs, "Со временем", "Слой ETL").  See GOTCHAS #14.

```bash
.venv/bin/python scripts/build_plan.py
```

Writes `edit/cuts.json`, `edit/stats.json` and `edit/topics_edited.json`.
`build_plan.py --help` lists every dial; the defaults produced episode 1:

| dial | default | what it does |
|------|---------|---------------|
| `--over` | 0.70 | silences longer than this are shortened rather than removed |
| `--keep-edge` | 0.16 | seconds of silence kept at each edge of a short pause |
| `--keep-long` | 0.10 | seconds kept at each edge of a pause over `--long-above` |
| `--long-above` | 1.30 | pause length that switches to the aggressive tier |
| `--min-cut` | 0.12 | ignore cuts shorter than this |
| `--motion-max` | 1.2 | skip a cut if average screen motion around it is higher |
| `--edge-max-db` | −30.0 | skip a cut if audio at either splice edge is louder (word tail) |
| `--head-trim` / `--tail-pad` | 1.2 / 1.0 | dead air removed at the very start, added at the very end |
| `--fps` | 25.0 | frame grid all kept boundaries are snapped to |
| `--duration` | 0 (ffprobe) | source duration |

Episode 1 result: 22 topics, 413 cuts, −338.4 s (5.15 %), 414 kept intervals,
`edited_duration` 6238.56 s exactly.

`edit/stats.json` records where the cuts came from and how many were rejected:
`silences_cut` 414, `skipped_drawing` 17, `skipped_loud_edge` 9, plus the
parameters used.  When the total looks wrong, this file says which rule is
doing the work.

**Check before continuing:**

```bash
.venv/bin/python - <<'PY'
import json
p=json.load(open("/media/timoti/Storage/Work/vidproj/edit/cuts.json"))
k=p["kept"]
print("cuts",len(p["cuts"]),"kept",len(k),"edited",round(p["edited_duration"],3))
print("monotonic:",all(k[i][1]<=k[i+1][0] for i in range(len(k)-1)))
print("snapped to 25 fps:",all(abs(round(a*25)-a*25)<1e-6 and abs(round(b*25)-b*25)<1e-6 for a,b in k))
print("sum == duration:",abs(sum(b-a for a,b in k)-p["edited_duration"])<1e-6)
PY
```

---

## 9. Dashboard visibility gates

```bash
.venv/bin/python scripts/panel_gates.py
```

The dashboard may only be drawn where the screen is not already using that
space.  The script measures, per sampled frame, the share of *ink* (dark or
strongly saturated pixels) inside the dashboard rectangle and writes the
ranges where it stays under `dashboard.visible_ink_share` (episode 1: 1.5 %) in
**edited** seconds.  The other thresholds are `style.json` keys
(`gate_pad_source`, `gate_merge_source`, `gate_min_visible_source`,
`gate_min_hidden_source`) and `--help` overrides them.

Run it **after** step 8: source seconds become edited seconds through
`edit/cuts.json`.

Episode 1: 8 visible ranges, hidden 340.4 s (5.5 % of 6238.56 s), first hidden
range 829.22–846.86 s edited — the lecturer opens a browser tab in the right
column to show a webpage.  The ink measure is deliberately simple and biased in
one direction: hiding a little too eagerly is fine, covering the lecturer's
content is not.

---

## 10. Plate and dashboard probe (before any long render)

```bash
.venv/bin/python scripts/make_plate.py          # render/panel_plate.png
.venv/bin/python scripts/probe_dashboard.py     # pass/fail, no video needed
```

`make_plate.py` draws the rounded translucent plate as an RGBA PNG with
alpha **premultiplied**, because ffmpeg's `overlay` does straight-alpha blending,
not Porter-Duff Src-over (DECISIONS #7).  `render.py` regenerates it whenever
`style.json` is newer than the PNG, so you rarely need to run this by hand.

`probe_dashboard.py` encodes the *real* dashboard graph twice — over a flat
canvas colour and over a busy moving pattern — and measures: corners really are
rounded, effective alpha matches the authored one, glyph contrast against the
plate the glyphs sit on is ≥ 4:1, tesseract reads every topic label, nothing is
drawn inside the corner squares.  Half a minute instead of a 21-minute render
that turns out unreadable.  Run it after every `style.json` change — it is the
only check that catches a palette change making the text illegible.

Episode 1 verdict (no pills, Manrope, plate at 0.66):

```
effective alpha 0.674 (authored 0.66)   contrast 5.05:1 flat / 4.89:1 busy
OCR 22/22 labels readable (flat canvas and busy background)
FIT 0/4 corner squares covered by drawing            VERDICT: PASS
```

`--keep` leaves `work/probe_*.mp4` and the per-row crops for looking at,
`--topics` probes a different topic map.

---

## 11. Audio cut (outside ffmpeg)

```bash
.venv/bin/python scripts/cut_audio.py           # render/audio_cut.wav
.venv/bin/python scripts/cut_audio.py --dry-run # report only
```

`aselect` keeps audio in 1024-sample blocks, so filtering audio with the same
interval list as video gains or loses up to 40 ms at every boundary; with 414
boundaries that is 16 s of drift plus audible clicks.  `cut_audio.py` slices a
sample-accurate WAV at the frame-snapped boundaries instead, so audio and video
agree exactly, and `render.py` muxes this WAV instead of filtering source audio.

Episode 1: `audio_cut.wav` 6238.560 s, video content 6238.560 s, cross-correlation
against the source at the first and last kept interval 1.0000.

---

## 12. Render

```bash
.venv/bin/python scripts/render.py                    # cards + content + concat
.venv/bin/python scripts/render.py --only content     # just the body
.venv/bin/python scripts/render.py --test 120         # 2-minute smoke render
.venv/bin/python scripts/render.py --preset draft     # fast, style checks only
.venv/bin/python scripts/render.py --vaqp 24          # override VAAPI quality
```

`render.py` reads `edit/style.json`, `edit/cuts.json`, `edit/panel_gates.json`,
`edit/topics*.json` and rebuilds `render/panel_plate.png` when `style.json` is
newer.  The generated filter graph is written to `render/filter_content.txt` —
keep it, it is the only readable record of what was actually rendered.

Stages:

1. **cards** — intro and outro, generated from `edit/topics.json` (including the
   `recap` flags) plus the source title in `source/<id>.info.json`.  CPU encode,
   seconds each; `--only intro,outro,concat` re-makes and re-joins them without
   touching the 21-minute body.
2. **content** — the edited lecture with the dashboard, GPU encode.  Episode 1:
   6238.56 s out in 21 min, ffmpeg RSS flat at ~345 MB.
3. **concat** — intro + content + outro into `render/final.mp4` with `-c copy`
   (instant, and safe because the cards are encoded with the same codec, size,
   fps, pixel format and GOP as the content).

Two things about that one `select`:

- **Memory.** It is a single streaming predicate over the decoded stream, not
  414 `trim`+`concat` pairs, which is what keeps RSS flat while other things
  hold RAM (DECISIONS #3).
- **Frame indices, not seconds.** The predicate is `between(n,a,b)` on source
  frame numbers, not `between(t,start,end)`.  Comparing a double derived from a
  rational frame timestamp with a decimal constant has no tolerance, so a
  boundary frame is dropped roughly once every six cuts — 52 frames, 2.08 s of
  growing audio drift on episode 1, invisible in the container duration (GOTCHAS
  #25).  `assert_cfr()` refuses to render unless ffprobe confirms the source is
  constant 25 fps with the first frame at PTS 0, because frame indices only mean
  what the plan thinks they mean on a CFR source.

GPU flags come from `style.json/encode`: `vaapi_device`, `extra_hw_frames 16`
**before** `-i` (it is an input option; after `-i` it is ignored and the upload
pool overflows), `format=nv12,hwupload`, `h264_vaapi` with `global_quality`.
`scripts/gpu_free.py` checks the card first.  If VAAPI fails (a busy card can
reject `vp9_vaapi` with `EINVAL` while `h264_vaapi` works — GOTCHAS #8)
`render.py` falls back to CPU `libx264`.

---

## 13. Verify the result

```bash
.venv/bin/python scripts/verify_output.py render/final.mp4
```

Eight sections, each one a number a viewer would notice if it were wrong:

1. **container** — h264 1920x1080, `r_frame_rate` exactly 25/1, aac 48 kHz.
2. **duration** — `edited + intro + outro` within 2 s, plus how much shorter.
2b. **frame counts** — the video track holds exactly `round(edited·fps) +
   intro·fps + outro·fps` frames and is within a frame of its own audio track.
   This is the check that duration alone cannot replace.
3. **dashboard legible** — OCR of the plate at four timestamps chosen inside
   allowed gate ranges: the clock (`1:02:14 / 1:43:59`, both H:MM:SS) and three
   topic rows.
4. **progress rail** — share of the plate's left rail lit at 25 % and 75 % of
   the body: 0.29 and 0.79.
5. **gate behaviour** — the plate rectangle is compared with the *source* frame
   at the mapped source time: ~150 levels apart where the plate is drawn,
   0.1–1.1 levels (identical) inside hidden ranges.
6. **nothing audible was cut** — the loudest sample inside anything removed is
   −36.5 dB against a recording median of −30.2 dB, i.e. every cut replaced room
   tone with room tone (GOTCHAS #27 explains why measuring the surviving audio
   instead flags every splice).
7. **cards** — the intro headline shows ≥80 % of the title words (a truncated
   wrap fails), and every recap line is checked **one by one** at the y the
   renderer computed: ink where the line should be, plus at least one long word of
   that title read back (7/7 here).  Counting bullets in the OCR of the whole card
   — the previous check — missed a card that had lost its last line.

Every number it prints is also written to `render/verified.json`, so the record
of what was checked survives the session and a later episode can be compared
against this one.

Episode 1 final numbers: 156 389 frames = 6255.56 s of video against 6255.58 s
of audio (the 21 ms is AAC priming), plate hidden in 8 of the ranges
`panel_gates.json` lists, rail 29 % / 79 % lit, nothing removed above −36.5 dB.

---

## 14. Deliver

```bash
cp render/final.mp4 "/media/timoti/Storage/Work/<channel> - <episode>. <title> [монтаж 1ч44м].mp4"
```

Episode 1 went out as:

```
LearnToCode - Теоретическая часть - 01. Процесс обработки данных. Жизненный цикл данных. Понятие ETL-процесса [монтаж 1ч44м].mp4
```

ext4 limits a filename to 255 **bytes**, and Cyrillic costs two apiece: check
`printf %s "$name" | wc -c` rather than counting characters and being surprised
at the `cp`.

The master is `render/final.mp4` at `encode/global_quality` 20.  For a
size-limited copy (e-mail, Telegram) re-encode with the `style.json/delivery`
parameters — `libx264 -crf 28 -preset slow -pix_fmt yuv420p -c:a aac -b:a 128k
-movflags +faststart` — 6256 s in ~45 min on CPU, ~1.2 GB, dashboard unchanged
because the overlay is already burned into the master.
