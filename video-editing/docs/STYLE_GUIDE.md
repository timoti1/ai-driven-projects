# Style guide

The look of a LearnToCode lecture edit, and how to change any part of it
without breaking the rest.  Everything visual is read from `edit/style.json`
by `scripts/render.py` and `scripts/make_plate.py`; colours are `0xRRGGBB`,
geometry is pixels on a 1920x1080 canvas.

`style.json` is the single source of truth.  If a number is hard to find
here, it is not a house-style decision and should not be tuned casually.

---

## Identity

Dark instrument panel floating over the lecture.  Cold blue accent for
"current", green for "done", neutral grey-blue for everything waiting.  The
panel never fights the lecturer for attention: it sits in the grey margin of
the Paint canvas, and it disappears entirely the moment the lecturer needs
that space.

```
accent        0x39c6ff   current topic, progress rail, plate border
accent_done   0x7ee787   finished: tick and finished bar segment
track         0x23272f   empty bar trough, progress rail track
plate_bg      0x0b0f16   the translucent plate the panel is written on
card_bg       0x0b0f16   intro/outro cards (same colour, opaque)
text_primary  white      current topic only, and only bold
text_done     0xe8eef5   finished topics
text_upcoming 0xc4cfd9   topics that have not started
text_card_body 0xcfd8e3  intro/outro body copy
text_card_meta 0x9fb0c3  intro/outro metadata (counts, durations, footer)
```

Typography is **Manrope** (`fonts/Manrope-Semibold.ttf` for emphasis,
`fonts/Manrope-Medium.ttf` for body) — a geometric grotesque with complete
Cyrillic and fixed-width numerals, under the SIL Open Font License 1.1, so it
ships in `fonts/` with `fonts/OFL.txt` rather than being installed system-wide.

DejaVu Sans is kept for exactly one glyph: the ✓ tick.  Manrope has no U+2713,
and drawing the tick from a font that has it (`fonts.tick` in `style.json`) is
cheaper than mixing two typefaces anywhere else.  Do not "unify" this by
drawing the tick in Manrope — it renders as a blank box.

The hierarchy inside the dashboard is carried by three things at once, never
by brightness alone:

| state    | weight | colour               | extra                        |
|----------|--------|----------------------|------------------------------|
| current  | bold   | white                | accent dot + accent row bar  |
| done     | regular| 0xe8eef5 (lightest)  | accent ✓, full row bar       |
| upcoming | regular| 0xdde8f2 (dimmest)   | nothing but its own bar      |

Brightness order is upcoming < done < current, and the dimmest colour is chosen
so it still clears 4:1 against the plate itself (see "Legibility").  A row gets
a mark only for something that happened: a dot while it is on screen, a tick
once it is over.  An upcoming row has no mark at all — a row of empty markers
carries no information and reads as noise.

---

## The plate

The dashboard is written on a **rounded, translucent plate**, not directly on
the video:

```
dashboard.plate_alpha   0.66   how opaque the plate is (0.34 of the lecture shows through)
dashboard.plate_radius  22     corner radius in px
dashboard.plate_bg      0x14191f
dashboard.plate_border_w     2      accent border, separates plate from the grey canvas
dashboard.plate_border_alpha 0.85
dashboard.rail_inset    4      the accent border doubles as the progress rail, inset px
dashboard.plate_png     render/panel_plate.png   generated, do not hand-edit
```

Two non-obvious things about it:

1. **The PNG is generated with premultiplied alpha** (`make_plate.py`).
   ffmpeg's `overlay` blends `out = in*(1-a) + over`, i.e. straight alpha.
   A PNG authored with plain (non-premultiplied) alpha makes the plate 26 %
   darker than the authored alpha, and the border colour bleeds into the
   corners.  Never replace `panel_plate.png` with a hand-drawn PNG; regenerate
   it so the premultiplication stays correct.
2. **The rounded corners are why the plate is not a `drawbox`.**  drawbox has
   no radius.  A PNG overlaid with `eof_action=repeat` and `format=auto` is how
   a rounded rectangle gets into the filter graph, and `format=auto` matters
   because `overlay`'s own `format` option has its own enum and rejects
   `yuva420p` with an error that looks unrelated.

`plate_alpha` is the dial that decides how much of the lecture you can see
behind the panel.  0.66 was chosen because the lecturer's canvas is a nearly
flat grey: at 0.66 the plate reads as one solid object, and the third that
bleeds through still tells you the plate is floating rather than painted on.

The other half of that decision is `plate_bg`.  It used to be a very dark navy
(0x0b0f16); with the pills gone, the plate *is* the text's background, so it was
lightened to a neutral grey (0x14191f) — a lighter base is what buys the
transparency back.  Measured: at 0.66 on 0x14191f the labels read 5.05:1 on a
flat canvas and 4.89:1 over a busy moving pattern; at 0.62 on 0x0b0f16 the same
text measured 3.59:1 and failed.  Dropping `plate_alpha` further without
lightening `plate_bg` is the failure mode, and `probe_dashboard.py` is what
catches it.

`plate_radius` is deliberately large relative to the 320 px width (22 px ≈
7 % of the width) so the plate reads as a card, not as a rectangle with
mitered corners.

---

## No per-row pills

Labels are plain text on the plate.  They used to sit on their own dark chips
(`drawtext box=1`), which solved legibility but made the panel read as a stack
of buttons instead of a table of contents:

```
dashboard.text_box         false
dashboard.text_box_color   0x000000@0.42   still there, only used if text_box is true
dashboard.text_box_borderw 8
dashboard.text_border_w    2
dashboard.text_border_color 0x000000@0.60  outline that stops anti-aliased edges from glowing
```

Legibility then comes from the plate colour plus a 2 px outline, and it is
measured, not assumed: **4.80:1** on a flat canvas and **4.93:1** over a busy
moving pattern (glyph against the surface it is actually drawn on), and every
label a viewer is meant to read is read back by tesseract
(`probe_dashboard.py`).  The outline is doing real work — with a 1 px outline at
the same plate settings the same text measured 3.59:1.

## Row states: dim, bright, live

A row's colour carries its state, so the panel reads peripherally without being
read at all:

| state | colour | weight | marker | glyph/plate (measured) |
|---|---|---|---|---|
| not reached yet | `palette.text_upcoming` `0x8a95a2` | regular | — | **1.48:1** |
| finished | `palette.text_done` `0xe8eef5` | regular | `✓` | **2.31:1** |
| happening now | `palette.text_primary` white | bold | dot | **2.5:1** |

Upcoming rows are *supposed* to be barely visible: 22 rows at full brightness
make one wall of equal text, and the live row stops standing out (DECISIONS 17).
The dim colour is still checked — `palette.min_upcoming_contrast` (1.35:1) keeps
it findable, and the probe requires upcoming rows to measure at most 0.8× a
finished row, so the hierarchy is measured rather than declared.

Static panel furniture — the heading, the total duration next to the clock — uses
`text_done`, not the dim colour.  Dim means "has not happened yet"; putting
permanent text in that colour would make it read as something pending.

`text_box` is kept as a switch rather than deleted because a future episode may
be recorded over a bright slide deck instead of a grey Paint canvas.  If
`probe_dashboard.py` ever reports under 4:1 on the busy background, set it back
to `true`; the plate does not have to get more opaque to fix that.

---

## Geometry

```
dashboard.layout    right_column
dashboard.panel_x   1600     plate left edge
dashboard.panel_w   320      plate width
dashboard.panel_y   77       plate top edge (lowered 15 px on request; the plate
                             still covers the same 340.4 s of browser activity)
dashboard.panel_h   896      plate height
dashboard.list_y    167      first topic row (moves with panel_y: the header band
                             between them is what the plate's hairline divides)
dashboard.row_h     34       row pitch; render.py grows or shrinks it to fill the plate
dashboard.row_h_max 44       never taller than this, even with two topics
dashboard.row_bottom_clear 16  rows stop this far above the plate's bottom edge
dashboard.row_fontsize 15
dashboard.row_bar_h 3        per-row progress bar under each label
dashboard.tick_fontsize 17   the ✓ (drawn in fonts.tick)
dashboard.marker_dot 7       the square dot that marks the current row, px
dashboard.clock_fontsize 26       elapsed clock
dashboard.clock_total_fontsize 18 total duration, next to it
dashboard.clock_gap 12       px between them (a 1 px divider sits between the two)
dashboard.header_fontsize 13
dashboard.list_header "ТЕМЫ ВЫПУСКА"
dashboard.progress_steps 8   per-row bar quantisation
dashboard.global_steps 40    overall rail quantisation
dashboard.global_bar_w  4
```

Why the right column: this is a screen recording of MS Paint, and Paint's
canvas stops short of the screen edge.  Below the ribbon (`y > 110`) and above
the taskbar (`y < 1010`), everything from `x = 1600` to the edge is empty grey
margin, so an overlay there covers nothing the lecturer does.  A bottom strip
would have covered the drawing area, and a mosaic along the bottom covered
about 12 % of the picture for no gain.

`row_h` is a *starting* pitch, not a fixed one.  `dashboard_layout()` computes
the room between `list_y` and the plate's bottom edge minus `row_bottom_clear`, divides by the topic count and clamps the result to `row_h`…`row_h_max`, then
shrinks the font if the row would not hold it.  A 30-topic episode keeps the
same plate and gets 27 px rows automatically; a 12-topic episode gets taller
rows instead of a plate that ends in an empty band.  Nothing is re-measured by
hand.

The clock and the heading above the list are positioned from `RULE_Y` — the
plate-local y of the hairline that is baked into the plate PNG.  `make_plate.py`
imports it from `render.py` instead of recomputing it, which is the only reason
the rule cannot drift away from the text above it.

Labels are fit to the space by measurement, not by hand-trimming:
`render.py` asks PIL how wide the string is in the chosen font and, if it does
not fit, shortens the font, then wraps.  That is how "Этапы S1…Sn" and
"Корпоративная БД" both fit in 278 px on any machine, with no dependency on
fonts being preinstalled.

---

## Visibility gates

The plate is not drawn when the lecturer is using that part of the screen:

```
dashboard.visible_ink_share      0.015  share of ink in the plate rect that hides it
dashboard.gate_pad_source        1.0    s of slack around each detected occupancy stretch
dashboard.gate_merge_source      4.0    s: occupancies closer than this merge
dashboard.gate_min_visible_source 6.0   s: shorter clear stretches are swallowed (anti-flicker)
dashboard.gate_min_hidden_source   2.0   s: shorter occupancies are ignored
(episode 1's gates were produced by exactly these numbers; `panel_gates.py
--help` overrides any of them for an experiment)
```

`scripts/panel_gates.py` measures occupancy from the 2 fps thumbnails
(`work/thumbs2fps.npy`) and writes `edit/panel_gates.json` in **edited**
seconds.  `render.py` ANDs those windows into every dashboard filter's
`enable` expression, so plate, border, clock, labels, ticks and bars all
vanish and reappear together — no half-drawn panel.

The thresholds are deliberately loose in one direction only: it is acceptable
for the panel to hide a little too eagerly, and not acceptable for it to cover
the lecturer's content.  Episode 1 hides for 340 s (5.5 %), all of it where a
browser tab was opened in the right column.

---

## Cards (intro and outro)

```
cards.intro_dur  7.0
cards.outro_dur  10.0
cards.lesson_fontsize     42    channel / lesson line
cards.title_fontsize      52    episode title
cards.title_max_width   1680    wrap width, 20 px margin each side
cards.meta_fontsize       30    duration, topic count line
cards.outro_heading       "Что разобрали в этом выпуске"
cards.recap_fontsize      26    one line per recap topic
cards.recap_line_mult     1.45  line pitch as a multiple of the font size
cards.recap_bottom        940   the list must end above this y
cards.outro_next     "Продолжение следует"
```

Wording rules, both of them earned the hard way:

- **"урок" is wrong.**  These are episodes of a course, not lessons; the
  lecturer says "выпуск"/"лекция".  The heading above says "выпуск" and the
  dashboard header says "ТЕМЫ ВЫПУСКА".
- **The title must fit.**  The source title is reused verbatim, so
  `render.py` measures it and wraps at `title_max_width`, shrinking the font
  only if two lines still do not fit.  A 52 px title that needs 2356 px on a
  1680 px canvas is how the first render looked cut off on the right.

The outro lists a *sample* of topics, not all 22 — a wall of 22 lines at 26 px
does not fit and is not worth reading.  Which topics are chosen is **not** a
style setting: the topics carry `"recap": true` in `edit/topics.json`, next to
the line they name.  It used to be `cards.recap_pick = [1,5,8,11,13,19,22]` here,
and when a topic was deleted from this episode the list quietly fell out of range
and the card drew 6 of 7 lines (GOTCHAS #32).

`recap_line_mult` is a multiplier, not a pixel height: when the list does not fit
above `recap_bottom`, the font shrinks and the spacing shrinks with it.  (The old
key `recap_line_h: 46` was an absolute height that nothing read — a style key that
looks like a setting but is never used is worse than no key.)

---

## Motion and sound

```
transitions.content_fade_in   0.5     fade from black into the lecture
transitions.content_fade_out  1.2     fade to black before the outro
transitions.intro_fade_in     0.8
transitions.intro_fade_out    0.9
transitions.outro_fade_in     0.6
transitions.outro_fade_out    1.6
audio.highpass 70             Hz, removes desk rumble
audio.denoise_nr 11 / denoise_nf -32   light broadband denoise, tuned not to eat consonants
audio.dynaudnorm_*            frame-normalising compressor (250 ms frames, gain 13, peak 0.45)
audio.limiter 0.95            final ceiling, 0.95 of full scale
audio.bitrate 160k / sample_rate 48000
```

The audio chain is applied once, to the whole edit, by `render/audio_cut.wav`
+ these filters in `render.py`'s audio chain.  Normalising audio *before*
cutting is a mistake: the normaliser looks at neighbours across a cut and
pumps.  160k AAC is transparent enough for speech at 1080p25.

`delivery` (codec/crf/preset/pix_fmt/audio) is the *size-limited copy*: CRF 28
`libx264` + 128k AAC + faststart, ~1.2 GB for a 1 h 44 min episode.  The master
is always rendered at `encode/`, never at `delivery/`, because a delivery copy
is re-encoded from a master, not from the analysis.: on this source
(talking head + text on white canvas) QP 20 keeps 15 px dashboard text crisp.
`encode.gop` 50 = 2 s keyframe interval so seeking is cheap; 25 would double
the file for no visible gain.  `--preset draft` (crf/qp 30, `veryfast`) is for
test renders only — dashboard text visibly smears at QP 30 in motion.

---

## Legibility, measured

The look is not a matter of taste here, because the dashboard has to survive a
2-hour lecture on a small laptop screen.  `scripts/probe_dashboard.py` encodes
the real dashboard over (a) a flat canvas colour and (b) a busy moving pattern
and asserts:

- corners of the plate are actually transparent (rounded, not square);
- effective alpha measured from a clean patch within 0.05 of `plate_alpha`;
- glyph contrast ≥ 4:1 against the surface it is drawn on, on both backgrounds
  (this is what broke when the pills went away, and it is what keeps it fixed);
- for the rows a viewer reads — the live row and the finished ones above it —
  tesseract reads the label back, on both backgrounds;
- for rows not reached yet: there is ink, it is above
  `palette.min_upcoming_contrast`, and it measures ≤ 0.8× a finished row.  They
  are deliberately faint, so holding them to the same bar as the live row would
  fail the design instead of the defect;
- nothing is drawn inside the rounded corner squares.

Run it after every `style.json` change; it costs half a minute and it is the
only thing standing between a typo and a 21-minute render.
