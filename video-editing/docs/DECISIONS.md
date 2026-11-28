# Decisions

Why the pipeline is shaped like this.  Each entry is the reason, what the
alternative was, and what breaks if you "simplify" it.

---

## 1. Cuts are derived from measurement, not from a shot list

**Decision.**  Silence intervals, measured speech spans, per-frame loudness,
screen-motion and slide OCR all get intersected before a single cut is
proposed; the editor chooses a topic map, the script chooses the scalpels.

**Why.**  A 1 h 49 min screen-recorded lecture contains ~758 s of measured
pause across 932 silences.  Cutting those by ear means watching 10 000 seconds.
Cutting them blindly means cutting words.  With a measured speech floor
(−37.6 dB) and a measured silence median (−57.1 dB) there is a 20 dB margin in
which a cut is provably inside dead air, and the script can be trusted to find
every one.

**Alternative rejected.**  One `silencedetect` pass fed straight into
`select`: it cuts through word tails and through drawing pauses, and the
result sounds chopped.

**Breaks if you change it.**  Drop `--edge-max-db` or `--motion-max` and the
next episode clips word endings and jumps over pen strokes.  Those two rules
are what "аккуратненько" means in code.

---

## 2. Frame-grid snapping of every kept boundary

**Decision.**  All kept intervals are snapped to the source frame grid
(`--fps`, default 25) in `build_plan.py`.

**Why.**  A boundary at 412.34 s on a 25 fps stream means frame 412.32 or
412.36, i.e. ffmpeg duplicates or drops a frame at each of 414 boundaries, and
the output duration stops being a sum of frame durations.  After snapping,
`edited_duration` is *exactly* `frames / fps` (6238.56 s) and audio slicing,
the dashboard timeline and `verify_output.py` all agree without tolerances.

**Breaks if you change it.**  A non-snapped plan drifts a few ms per cut, and
the dashboard's topic timings drift with it, so the green tick appears ~0.2 s
late by the end of a 1 h 44 min episode.

---

## 3. One `select` filter instead of 414 `trim`+`concat` pairs

**Decision.**  The body is `[0:v]select='between(t,a,b)+between(t,...)+...'`.

**Why.**  The obvious expression — `split=414` then 414 `trim`s into `concat` —
made ffmpeg hold hundreds of decoded frames and a filter graph whose memory grew
until the process died.  This machine routinely runs ~54 GB of llama.cpp models
in the same box.  `select` keeps RSS flat at ~345 MB and takes the same wall-clock
time, because decoding is the cost either way.

**Alternative rejected.**  `trim`/`concat` (memory blow-up), and cutting into
segments on disk then muxing (`concat demuxer` with 414 files: 414 seek points,
keyframe-aligned so it loses the fine cuts — 0.12 s cuts become 2 s cuts).

**Breaks if you change it.**  `select` alone does *not* renumber timestamps:
see #4.  And a 414-term expression is 143 KB of filtergraph text — fine as a
`-filter_complex_script` file, painful on a command line.

---

## 4. `setpts=N/FRAME_RATE/TB`, not `setpts=PTS-STARTPTS`

**Decision.**  After `select`, timestamps are renumbered frame-by-frame.

**Why.**  `select` throws frames but keeps their original PTS.  Subtracting the
first PTS leaves *gaps* where frames were removed; the following `fps=25` then
fills each gap with a duplicated frame — the output comes out at (almost) the
original length with 414 freeze-frames in it.  That looked like "the cut did
nothing" until durations were compared.  `N/FRAME_RATE/TB` produces a dense,
gapless 25 fps stream, and it is also what makes the audio cut (#5) line up.

**Breaks if you change it.**  Any expression that shifts rather than renumbers
(`PTS-STARTPTS`, `setpts=pts`) silently un-does the edit and stretches the
dashboard overlay relative to the picture.

---

## 5. Audio is cut outside ffmpeg

**Decision.**  `cut_audio.py` writes `render/audio_cut.wav` by slicing a
sample-accurate WAV at the frame-snapped boundaries; `render.py` muxes that WAV.

**Why.**  `aselect` operates on 1024-sample blocks (21.3 ms at 48 kHz), so each
of 414 boundaries keeps or drops a partial block: up to 40 ms per boundary, ~16 s
over the episode, plus a click at every splice because the waveform is cut
mid-cycle.  Sample-exact slicing has neither problem, and it lets `verify_output.py`
compare audio against the plan by cross-correlation (1.0000 at first and last
interval) instead of by ear.

**Alternative rejected.**  `atrim`+`concat` for audio (same block quantisation,
plus 414 concat nodes), and `async=1` resampling (hides the error, does not fix
it, and smears transients).

**Breaks if you change it.**  Muxing the source audio with `aselect` re-introduces
the drift; the dashboard (built from edited seconds) then disagrees with what you
hear — topic N marked done while the lecturer is still on it.

---

## 6. The dashboard lives in the right margin, on a plate, and hides when occupied

**Decision.**  A 320 px column at x=1600, on a rounded translucent plate, drawn
only where `panel_gates.json` allows it.

**Why.**  The source is a MS Paint recording: Paint's canvas stops short of the
screen edge, so below the ribbon and above the taskbar the strip `x ≥ 1600` is
empty grey for most of the runtime.  A bottom strip would cover the drawing area
(a bottom mosaic covered ~12 % of the picture for no gain — that was the first
attempt).  A plate is used rather than free-floating text because the strip is
not empty the whole time: the lecturer opens a browser tab there from 13:49 to
20:30 (source).  `panel_gates.py` measures ink inside the footprint and hides
the whole dashboard — plate, border, clock, labels, ticks, bars — for those
340 s.  A translucent plate that lets a webpage show through looks like a bug;
the plate either belongs there or it is gone.

**Breaks if you change it.**  Move the plate left of x=1600 and it covers the
lecturer's canvas.  Make the gates stricter (lower `visible_ink_share`) and it
hides during harmless mouse movement; looser, and it overlaps content.  Hide the
plate but not the text (or vice versa) and the panel looks broken for a minute.

---

## 7. Plate = premultiplied RGBA PNG overlaid with `eof_action=repeat`, `format=auto`

**Decision.**  `make_plate.py` draws the plate with PIL and bakes alpha
premultiplication into the PNG; `render.py` overlays it as input 2.

**Why.**  ffmpeg has no rounded rectangle: `drawbox` cannot do radius.  A PNG is
the only way to get corners.  And `overlay` blends `out = in*(1-a) + over*a`
(straight alpha), so a normal PNG authored at 72 % alpha over a dark fill lands
about 26 % darker than intended and the accent border bleeds into the corner
anti-aliasing.  Premultiplying in the PNG is what makes measured alpha come out
at 0.674 for an authored 0.66.  `format=auto` is required because `overlay`'s own
`format` option has its own enum and rejects `yuva420p` with an error message
about pixel formats that sends you debugging the wrong thing.

**Alternative rejected.**  `geq`/`drawbox` combos (no rounded corners, CPU
per-pixel), and `boxblur`+`colorchannelmixer` tricks (translucency without a
shape).

**Breaks if you change it.**  Hand-drawing the PNG (GIMP, Inkscape export)
re-introduces straight alpha and the plate darkens.  Regenerate instead.

---

## 8. No pills: the plate itself is the text's background

**Decision.**  Topic rows are plain text.  `text_box` is `false`; legibility
comes from the plate colour (`plate_bg 0x14191f`, a neutral grey) plus a 2 px
black@0.60 outline on every glyph.  Rows also lost their highlight band: a dot
marks the row you are on, a ✓ marks a row you finished, an upcoming row gets
nothing but its own progress bar.

**Why.**  Pills made every row look like a button, so the panel read as a menu
of things to click rather than a table of contents to read; the same objection
applied to the green highlight band, which made three rows look active at once.
The honest question was whether the plate alone can carry the text, and the
answer is measurable: 5.05:1 on a flat canvas and 4.89:1 over a busy moving
pattern, with 22/22 labels read back by tesseract — all while the plate got
*more* transparent (0.72 → 0.66), not less.

What makes that work is `plate_bg`, not `plate_alpha`.  The first attempt at
this design kept the old near-black navy plate (0x0b0f16) at alpha 0.62 and
measured **3.59:1** — a fail.  Lightening the plate to a neutral grey is what
bought the transparency back.  A 1 px outline instead of 2 px at the same
settings also measured 3.59:1: the outline is doing real work, it is not
decoration.

**Breaks if you change it.**  Lower `plate_alpha` or darken `plate_bg` without
re-measuring and the labels fall under 4:1 — on a grey Paint canvas they may
still look fine to you while tesseract stops reading them, which is the same
thing happening to a viewer on a dim laptop.  `probe_dashboard.py` measures it in
half a minute; run it after any change to `palette` or `text_border_*`.  If a
future episode is recorded over a bright slide deck rather than a grey canvas,
set `text_box` back to `true` rather than making the plate opaque.

---

## 9. The panel is a table of contents in the field's vocabulary, anchored to speech

**Decision.**  A row is named for the **concept being demonstrated**, not for the
incidental example that demonstrated it, and not by quoting the speaker.  The
panel of this episode reads as a data-engineering table of contents:
структурированные → полуструктурированные → неструктурированные данные, форматы,
Data Lake, then the pipeline stages (извлечение, фильтрация, очистка,
токенизация, скраппинг, агрегация), этапы, «структуры больше, данных меньше»,
хранение, инструменты, выводы.

Three rules, all enforced or checkable:

- **Example ≠ topic.**  "Перегородки и доллары" is an illustration of what an ETL
  process does, so the row is «Аналогии, объясняющие ETL».  Pictures and audio are
  examples of unstructured data, so the row names the category, not «картинки,
  аудио».  A diagram is drawn at 3860 s, so that row is «Диаграмма: этапы и объём
  работ», not «объём работы».
- **Industry terms stay in English and are never translated or transliterated:**
  `Data Lake`, `ETL`, `Spark`, `Power BI` — not «Дейта Лейк», not «озеро данных».
  (The earlier fix in the other direction — «Пруд vs океан» → «Лейк и оушен» — was
  still wrong: the field says Data Lake.)
- **Every row carries an `anchor`** — a word the lecturer really says inside its
  window.  `scripts/audit_titles.py` lemmatises the window with pymorphy3 and
  fails the run when the anchor is absent.  With an anchor, words in the title
  that are not spoken («Аналогии», «Диаграмма», «Выводы», «Инструменты») are
  reported as notes: they are the editor's domain vocabulary, which is what makes
  the panel an оглавление rather than a transcript.  Without an anchor the old
  strict rule still applies, so a general name cannot be a guess.

**Why.**  The first pass invented titles ("БД vs ТВ", "Кривая усилий: от хаоса к
порядку", "Слой ETL") — a summarised title is a promise the minute does not keep.
Its mirror-image failure is titling by the example: "Перегородки валюты" is
literally what he says, and tells a viewer nothing about a data-engineering
lecture.  Anchors are what let us fix the second failure without reopening the
first: the name is general, the anchor proves the row points at real content, and
the whole map is still machine-checkable (22/22 anchors found in their windows).

**Breaks if you change it.**  Invented titles make the outro recap lie.  Example
-titled rows make the panel useless as a course outline: nobody searching for
"Data Lake" or "агрегация" finds them, and the recap at the end stops being a
summary of the subject.

---

## 17. Rows you have not reached are dim; rows you have passed are bright

**Decision.**  A panel row is drawn in one of three colours by its state, not one
colour with a marker: upcoming `0x8a95a2` (deliberately recessive), finished
`0xe8eef5` + a `✓`, the live row white + bold + a dot marker.  Measured glyph/plate
contrast: upcoming ~1.5:1, finished ~2.3:1, live ~2.5:1.

**Why.**  The panel has 22 rows and the viewer reads one of them.  Drawing the
other 21 at full brightness makes the column look like a wall of equal text, and
the row that matters does not stand out.  Dimming what has not happened yet turns
the panel into a progress indicator you can read peripherally: the bright block
above the live row *is* "how far we've got", and it grows as the lecture runs.

**How it is verified.**  `probe_dashboard.py` no longer holds every row to the
≥4:1 rule (that would fail the design on purpose).  It classifies rows by state
at the probe time, requires ≥4:1 local contrast and OCR for the rows a viewer
reads, and for upcoming rows requires ink, a visibility floor
(`palette.min_upcoming_contrast` = 1.35:1, so they are faint but never invisible)
and that they measure at most 0.8× a finished row — the hierarchy has to be real,
not declared.  `verify_output.py` checks the same thing on the rendered file.

**Breaks if you change it.**  A per-row mean of ink pixels is the wrong measure
(GOTCHAS 33): the 75th percentile is used, otherwise a long label looks fainter
than a short one at the same colour and the check measures label length instead of
colour.

---

## 10. Cards are encoded to match the body, then joined with `-c copy`

**Decision.**  Intro/outro are rendered separately with the same encoder
settings (codec, GOP, size, fps, pixel format) as the body, and `concat` is a
demuxer copy.

**Why.**  A re-encode of the whole delivery would mean 1 h 44 min of encoding
for 17 seconds of cards, and a second generation of compression artefacts on
text-crisp 1080p25.  With matching stream parameters the join is instant and
lossless, and the cards can be re-made and re-joined in seconds when the wording
changes (which it did: "урок" → "выпуск", title wrap).

**Breaks if you change it.**  Different GOP or pixel format between cards and
body makes the copy produce a file that plays with a hiccup at the joins, or a
player that refuses to seek.  That is why `style.json/encode/gop` applies to all
three renders.

---

## 11. VAAPI on the encoder card, CPU fallback

**Decision.**  `h264_vaapi` on `/dev/dri/renderD128` (Sapphire RX 9070),
`extra_hw_frames 16` as an *input* option, `scripts/gpu_free.py` consulted
first, CPU `libx264` fallback if VAAPI errors.

**Why.**  GPU encode ran 6238 s of 1080p25 out in ~21 min (~5x realtime) while
CPU `libx264 -preset veryfast` on 16 threads took ~50 min for the same file, and
the two cards are not interchangeable: renderD129 runs the llama.cpp models, so
encoding must not fight it for the media engine.  `extra_hw_frames` before `-i`
matters: after `-i` it is ignored, the upload pool overflows and you get
"Hardware frame pool exhausted" or EINVAL on `vp9_vaapi`.

**Breaks if you change it.**  `vp9_vaapi` on this driver fails with EINVAL when
the card is under load while `h264_vaapi` still works (GOTCHAS #8) — so the
default codec is h264.  QP 30 (`--preset draft`) smears 15 px dashboard text in
motion; draft is for checking layout, never for delivery.

---

## 12. Legibility is tested numerically, because the operator cannot see

**Decision.**  `probe_dashboard.py` (before rendering) and
`verify_output.py` (after) assert corners, alpha, contrast, OCR readability,
rail growth, panel gating and A/V sync, all as numbers.

**Why.**  This pipeline is run by an agent that cannot look at a frame, and by a
person who does not want to watch 104 minutes to find one bad overlay.  Every
visual property that matters has been turned into something measurable: rounded
corners (transparent pixels in the corner squares), translucency (effective alpha
from a clean patch), contrast (glyphs vs the plate they sit on, on two
backgrounds), legibility (tesseract reads all 22 labels), progress (rail width
grows), gating (panel absent in a hidden range).

**Breaks if you change it.**  Skipping the probe costs a 21-minute render per
mistake; skipping `verify_output.py` costs discovering a 16 s A/V drift after you
have uploaded the file.

---

## 15. The panel clock shows H:MM:SS / H:MM:SS

**Decision.**  The running clock and the total next to it are both `H:MM:SS`,
separated by a 1 px divider; the slot reserved for the elapsed part is measured
at the widest value the clock will ever print, so the divider never moves while
the seconds tick.

**Why.**  It used to print `104:12 / 1:43:58`: two numbers in two different
formats side by side read as unrelated quantities, and a viewer has to work out
which is which.  `fmt_tc()` now always emits hours, which also means a 2-minute
test render shows `0:01:54` rather than `1:54` — the same shape as the real
delivery, so the smoke test actually tests the layout.

**Breaks if you change it.**  `TC_EXPR` (an ffmpeg `eif` expansion) and `fmt_tc()`
(Python) must produce the same shape; they live in different languages, so
`verify_output.py` checks the rendered frame with a regex for `H:MM:SS / H:MM:SS`
rather than trusting either one.

---

## 16. Manrope for text, DejaVu for the one glyph Manrope lacks

**Decision.**  Panel and card text is Manrope (Semibold for emphasis, Medium for
body), vendored in `fonts/` with `fonts/OFL.txt`.  `fonts.tick` points at DejaVu
Sans Bold for the ✓ only.

**Why.**  DejaVu Sans is a 2001 bitmap-era UI face: at 15 px in a panel that is
the first thing you look at, its even widths and loose spacing read as a terminal
listing.  Manrope is a geometric grotesque with full Cyrillic and tabular
numerals, and it is OFL-licensed, so it can be committed rather than installed.
Manrope has no U+2713, and pulling the tick from DejaVu costs one font entry and
keeps every other glyph in one typeface.

**Breaks if you change it.**  Set `fonts.tick` to Manrope and the tick renders as
a blank box; draw the tick as a `\u2713` escape sequence in the filter text and
`drawtext` prints the six literal characters `\u2713` instead — the glyph has to
be the actual character in the filter file (it is read from `dashboard.tick_glyph`
in `style.json`).  Both are silent: the render succeeds either way.

---

## 13. Style, gates and delivery live in one JSON

**Decision.**  `edit/style.json` holds palette, geometry, plate parameters, gate
thresholds, card copy, transitions, audio chain, encode and delivery parameters;
scripts read it with fallbacks.

**Why.**  The next episode must look like this one.  A new video should only
have to change `edit/topics.json` (video id, topics, titles, and which topics are
marked `recap`).  Anything that needs re-measuring per episode is a bug in this
design — which is why `row_h` is a starting pitch that adapts itself and why
labels are measured and wrapped instead of hand-trimmed.

The boundary between style and content is drawn by consequence, not by taste:
whatever belongs to *this* lecture lives in `edit/`, next to the data it describes.
`cards.recap_pick` used to live here, and after a topic was deleted it silently
selected the wrong topics and one recap line short (GOTCHAS #32).

**Breaks if you change it.**  A threshold that only exists as a constant inside
a script gets forgotten when the style is retuned for episode 2.  That was true
of the gate thresholds until now, which is why `panel_gates.py` reads them from
`style.json/dashboard` and keeps the old values as defaults.

## 14. Cuts select frame numbers, and verification counts frames

**Decision.**  `render.py` selects video with `between(n, first_frame,
last_frame)` instead of `between(t, start, end)`, refuses to render unless
ffprobe confirms the source is constant-frame-rate from PTS 0, and
`verify_output.py` checks the produced frame counts against the plan.

**Why.**  Time-based selection compares a double derived from a frame's
rational timestamp with a decimal constant and has no tolerance, so the frame
sitting exactly on a boundary is dropped about once every six cuts.  Episode 1
lost 52 frames that way — 2.08 s — and nothing in the old check list noticed,
because a container reports the duration of its *longest* track and the audio
track was exactly the planned length.  The defect was audio sliding away from
the picture, growing linearly to two seconds by the end: a lecture edit that
passes every duration check and is still wrong.

**Breaks if you change it.**  Frame-number selection is only equivalent to
seconds if the source is CFR with the first frame at PTS 0, which
`assert_cfr()` verifies rather than assumes; a variable-frame-rate screen
recording needs the seconds form back.  And a verifier that re-states the
numbers it is supposed to check has stopped checking them: the panel geometry
used to be copy-pasted into `verify_output.py`, which is why it kept measuring
the bottom strip after the dashboard moved to the right column.
