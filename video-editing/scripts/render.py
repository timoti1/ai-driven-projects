#!/usr/bin/env python3
"""
render.py -- build the ffmpeg graph and render the edited video.

  A) render/audio_cut.wav                (scripts/cut_audio.py, sample-exact)
  B) cuts + dashboard + audio cleanup -> render/content.mp4   (one encode)
  C) intro.mp4 / outro.mp4                                   (two short cards)
  D) concat demuxer, stream copy      -> render/final.mp4     (lossless join)

Why a single long encode: every extra full-length pass softens screen text.
The intro/outro joins are dip-to-black (fade out / fade in), so the assembly
needs no re-encode.

Why the audio is cut outside ffmpeg: aselect drops a whole 1024-sample audio
block whenever a cut falls inside it, which measured ~40 ms per cut and would
have run the narration 16 s early by the end. See scripts/cut_audio.py.

Text metrics come from PIL, so a title that is too wide for the canvas is
measured and wrapped or shrunk instead of silently running off the edge -- the
intro headline was 2356 px wide on a 1680 px card and lost half of its text.

  --test N   render only the first N seconds (fast visual check)
  --only     subset of: content,intro,outro,concat
"""
import argparse, json, os, subprocess, sys

try:
    from PIL import ImageFont
except ImportError:                                  # fit checks degrade to guesses
    ImageFont = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ID = "source/F6fCcoNNdEE.mp4"
R = os.path.join(ROOT, "render")
os.makedirs(R, exist_ok=True)

# House style lives in edit/style.json so the next video keeps the same look.
# Every key is optional; the values below are the defaults.
def _load_style():
    p = os.path.join(ROOT, "edit/style.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding="utf-8"))


_S = _load_style()
_P = _S.get("palette", {})
_D = _S.get("dashboard", {})
_C = _S.get("cards", {})
_T = _S.get("transitions", {})
_E = _S.get("encode", {})
_A = _S.get("audio", {})
_F = _S.get("fonts", {})

def _font(key, default):
    """
    Resolve a font path from style.json, failing loudly when it is missing.

    A relative path is taken from the project root, so a cloned tree finds its own
    fonts/ directory; an absolute path (a system font) still works.  A missing
    font has to stop the run here: ffmpeg either falls back to another face or
    dies inside a 20 minute encode, and neither tells you which key was wrong.
    """
    p = _F.get(key, default)
    if not os.path.isabs(p):
        p = os.path.join(ROOT, p)
    if not os.path.exists(p):
        raise SystemExit(f"style.json fonts.{key} points at a file that does not "
                         f"exist: {p}\n  put the font in fonts/ or set the key to a "
                         f"system path (fc-list | grep -i <name>)")
    return p


FONT = _font("bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_R = _font("regular", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

# Sapphire RX 9070 (ROCm0/HIP0, PCI 06:00.0 -> card1 -> renderD128). The
# Gigabyte card (renderD129) is normally busy serving models, so the edit
# encode is pinned to the Sapphire render node.
VAAPI_DEVICE = _E.get("vaapi_device", "/dev/dri/renderD128")
VA_CODEC = _E.get("codec", "h264_vaapi")
VA_QP = _E.get("global_quality", 20)
GOP = _E.get("gop", 50)
EXTRA_HW = _E.get("extra_hw_frames", 16)

W_CANVAS = _S.get("canvas", {}).get("width", 1920)
H_CANVAS = _S.get("canvas", {}).get("height", 1080)
FPS = _S.get("canvas", {}).get("fps", 25)

# Dashboard geometry: one narrow column down the right edge of the frame.
# On this recording Paint's canvas stops short of the screen edge, so x>=1600
# below the ribbon is empty grey canvas margin and hides nothing when covered.
# (Not for the whole lecture -- see panel_gates.py and edit/panel_gates.json.)
PANEL_X = _D.get("panel_x", 1600)
PANEL_W = _D.get("panel_w", 320)
PANEL_Y = _D.get("panel_y", 112)
PANEL_H = _D.get("panel_h", 896)
LIST_Y = _D.get("list_y", 186)
ROW_H_WANT = _D.get("row_h", 34)
ROW_FS_WANT = _D.get("row_fontsize", 15)
TICK_FS = _D.get("tick_fontsize", 17)
# Manrope has no U+2713, so the tick comes from a font that does; the glyph is
# a real character in the filter file (an earlier version passed the literal
# string \u2713, which drawtext printed as six ASCII characters).
TICK_FONT = _font("tick", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
TICK_GLYPH = _D.get("tick_glyph", "\u2713")
MARKER_DOT = int(_D.get("marker_dot", 7))
ROW_H_MAX = float(_D.get("row_h_max", 44))
ROW_CLEAR = int(_D.get("row_bottom_clear", 16))
CLOCK_FS = _D.get("clock_fontsize", 26)
CLOCK_TOTAL_FS = int(_D.get("clock_total_fontsize", 18))
CLOCK_GAP = int(_D.get("clock_gap", 12))
HEAD_FS = _D.get("header_fontsize", 13)

# Where the clock/heading block sits.  The hairline under it is baked into the
# plate PNG (make_plate.py), so its position is defined once here in plate-local
# coordinates and make_plate.py imports it -- two files computing the same line
# independently is how the rule and the text end up 6 px apart.
RULE_Y = min(LIST_Y - PANEL_Y - 10, 14 + HEAD_FS + 8 + CLOCK_FS + 12)
CLOCK_Y = PANEL_Y + 16
HEAD_Y = PANEL_Y + RULE_Y - 6 - HEAD_FS
LIST_HEAD = _D.get("list_header", "ТЕМЫ ВЫПУСКА")
ROW_BAR_H = _D.get("row_bar_h", 3)
STEPS = _D.get("progress_steps", 8)
GLOB_STEPS = _D.get("global_steps", 40)
GLOB_W = _D.get("global_bar_w", 4)

# The plate (rounded, translucent, see scripts/make_plate.py) replaces the old
# flat drawbox panel.  Its rounded outline is inset by plate_border_w, so the
# progress rail and the row highlight are inset a little too and never cross a
# corner arc.
PLATE = os.path.join(ROOT, _D.get("plate_png", "render/panel_plate.png"))
RAIL_INSET = _D.get("rail_inset", 4)
RAIL_X = PANEL_X + RAIL_INSET
RAIL_Y = PANEL_Y + RAIL_INSET * 2
RAIL_H = PANEL_H - RAIL_INSET * 4
TICK_X = RAIL_X + GLOB_W + 8
LABEL_X = TICK_X + 22
LABEL_W = PANEL_X + PANEL_W - RAIL_INSET - LABEL_X
# Thin dark outline on every dashboard glyph: keeps text crisp while the
# plate itself stays see-through (measured: 3.32:1 without it, 4.5:1+ with).
TEXT_BORDER_W = int(_D.get("text_border_w", 1))
TEXT_BORDER_COLOR = _D.get("text_border_color", "0x000000@0.55")
TEXT_EDGE = f"borderw={TEXT_BORDER_W}:bordercolor={TEXT_BORDER_COLOR}"
# Per-label dark boxes ("pills") were measured to be what made rows readable
# over a white Paint canvas, and they are still available -- but they made the
# panel read as a stack of buttons rather than a table of contents, so the
# default is off and legibility comes from the plate colour plus the 1 px
# outline.  probe_dashboard.py re-measures contrast on every style change; if
# rows ever drop below 4:1 again, set text_box back to true.
TEXT_BOX_COLOR = _D.get("text_box_color", "0x000000@0.42")
TEXT_BOX_PAD = int(_D.get("text_box_borderw", 5))
TEXT_BOX = (f"box=1:boxcolor={TEXT_BOX_COLOR}:boxborderw={TEXT_BOX_PAD}"
            if _D.get("text_box", False) else "")

ACCENT = _P.get("accent", "0x39c6ff")
ACCENT2 = _P.get("accent_done", "0x7ee787")
TRACK = _P.get("track", "0x23272f")
PANEL_BG = f"{_P.get('panel_bg', '0x10141b')}@{_P.get('panel_alpha', '0.80')}"
TXT_MAIN = _P.get("text_primary", "white")
# Hierarchy is carried by brightness: upcoming 0xc4cfd9 < done 0xe8eef5
# < current white+bold.  Upcoming used to be 0x8b97a7, which measured only
# 3.6:1 against its own pill -- fine for a human glance, too faint for OCR
# at 15 px, and 15 of 23 rows are "upcoming" at any moment.
TXT_CHIP = _P.get("text_done", _P.get("text_secondary", "0xdfe6ee"))
TXT_MUTE = _P.get("text_upcoming", "0xc4cfd9")
TXT_CARD = _P.get("text_card_body", "0xcfd8e3")
TXT_META = _P.get("text_card_meta", "0x9fb0c3")
CARD_BG = _P.get("card_bg", "0x0b0f16")

INTRO_DUR = _C.get("intro_dur", 7.0)
OUTRO_DUR = _C.get("outro_dur", 10.0)
CARD_X = _C.get("card_x", 120)
CARD_W = W_CANVAS - 2 * CARD_X
RECAP_X = _C.get("recap_x", 150)
RECAP_Y0 = _C.get("recap_y0", 300)
RECAP_FS = _C.get("recap_fontsize", 26)
# Which topics the outro card lists is a `"recap": true` flag on the topic in
# edit/topics.json -- see outro_layout().  It used to be an index list here, and
# an index list shifts silently when a topic is added or removed.
RECAP_BOTTOM = _C.get("recap_bottom", 940)
# Line pitch is a multiple of the font size, so shrinking the font to fit
# the card shrinks the spacing with it.
RECAP_LINE_MULT = _C.get("recap_line_mult", 1.45)

FADE_C_IN = _T.get("content_fade_in", 0.5)
FADE_C_OUT = _T.get("content_fade_out", 1.2)


# ---------------------------------------------------------------- text metrics

_FONTS = {}


def pil_font(path, size):
    if (path, size) not in _FONTS:
        _FONTS[(path, size)] = ImageFont.truetype(path, size)
    return _FONTS[(path, size)]


def text_w(s, path, size):
    """Rendered width of s in px. Without PIL this is a conservative guess."""
    if ImageFont is None:
        return len(s) * size * 0.62
    return pil_font(path, size).getlength(s)


def ascent(path, size):
    """Baseline offset above the drawtext y for this font at this size."""
    return pil_font(path, int(size)).getmetrics()[0]


def fit_fs(texts, path, max_w, want, floor=11):
    """Largest fontsize <= want at which every string fits max_w."""
    for fs in range(int(want), floor - 1, -1):
        if max(text_w(t, path, fs) for t in texts) <= max_w:
            return fs
    return floor


def wrap(s, path, size, max_w, max_lines=2):
    """Greedy word wrap; ellipsises instead of ever running off the card."""
    words, lines, cur = s.split(), [], ""
    for wd in words:
        cand = wd if not cur else cur + " " + wd
        if text_w(cand, path, size) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_w(last + "…", path, size) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,") + "…"
    return lines


# ------------------------------------------------------------------- ffmpeg io

def esc(s):
    """Escape a literal string for ffmpeg drawtext text='...'."""
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,")
    s = s.replace("'", "\u2019").replace(";", "\\;").replace("%", "\\%")
    return s


def fmt_tc(t):
    """H:MM:SS, always.  The panel prints the running clock and this total side
    by side; an MM:SS total next to an H:MM:SS clock (1:54 vs 0:01:00) reads as
    two unrelated numbers."""
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


# Each ':' in a drawtext text is read as an option separator unless escaped,
# and the timecode is built from eif expansions, so both the expression and
# the literal colon have to survive two layers of escaping.
# H:MM:SS, the same shape as fmt_tc() prints for the total -- an earlier
# version printed minutes-only (104:12) next to a 1:43:58 total, which reads
# as two unrelated numbers.
TC_EXPR = ("%{eif\\:trunc(t/3600)\\:d}\\:%"
           "{eif\\:trunc(mod(t\\,3600)/60)\\:d\\:2}\\:%"
           "{eif\\:trunc(mod(t\\,60))\\:d\\:2}")


def load():
    cuts = json.load(open(os.path.join(ROOT, "edit/cuts.json"), encoding="utf-8"))
    top = json.load(open(os.path.join(ROOT, "edit/topics_edited.json"),
                         encoding="utf-8"))
    meta = json.load(open(os.path.join(ROOT, "edit/topics.json"), encoding="utf-8"))
    return cuts, top, meta


def visibility_expr():
    """
    Time ranges (edited seconds) during which the dashboard may be drawn.

    edit/panel_gates.json comes from scripts/panel_gates.py, which measures
    how much of the right column the lecturer actually uses.  Without this the
    panel sits on top of a browser window the lecturer opens around 14:40 for
    several minutes.  Returning None means "always draw".
    """
    p = os.path.join(ROOT, "edit/panel_gates.json")
    if not os.path.exists(p):
        return None
    g = json.load(open(p, encoding="utf-8"))
    vis = g.get("visible") or []
    if not vis:
        return None
    if len(vis) == 1 and vis[0][0] <= 0.01 and vis[0][1] >= g.get("edited_duration", 1e9):
        return None
    return "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in vis)


VIS = visibility_expr()


def gate(expr):
    """AND a per-frame condition with the dashboard's visibility windows."""
    if expr is None:
        return f"enable='{VIS}'"
    if VIS is None:
        return f"enable='{expr}'"
    return f"enable='({expr})*({VIS})'"


def cut_filter(kept):
    """
    One streaming select filter holding every kept interval (video only).

    Two traps this formulation avoids:

    1. memory. The obvious [0:v]trim=...:end=... per interval followed by
       concat=n=414 makes ffmpeg auto-insert a `split` with 414 outputs, which
       decodes far ahead and buffers a frame per branch: 12.7 GB RSS and an
       OOM kill on a 104-minute 1080p lecture. select evaluates a per-frame
       predicate on one stream, so memory stays flat (~330 MB).

    2. retiming. setpts=PTS-STARTPTS only *shifts* timestamps by the first
       kept frame's PTS; the gaps between kept intervals stay in the timeline,
       and the following fps=25 fills every gap with duplicated frames. It
       looked fine and came out the full uncut length (6575 s instead of
       6238 s). Frames must be *renumbered*: setpts=N/FRAME_RATE/TB compacts
       the timeline so its length equals the sum of the kept ranges.

    3. boundary arithmetic. between(t,A,B) compares a double derived from the
       frame's rational PTS against a decimal constant, with no tolerance.
       Between two values that are mathematically equal, ffmpeg's rounding and
       the rounding of the parsed constant can disagree, and the frame exactly
       at the boundary is silently dropped: 52 of 155 964 frames went missing
       across 414 ranges, which is a lip-sync error that grows to 2.1 s by the
       end of the film -- invisible in the container duration, because the
       *audio* track is exactly the planned length and the muxer reports the
       longer stream.  between(n,A,B) on frame indices has no rounding at all,
       and it is exact because build_plan.py snaps every cut to the frame grid
       and the source is CFR (assert_cfr below).
    """
    expr = "+".join(f"between(n,{int(round(s * FPS))},{int(round(e * FPS)) - 1})"
                    for s, e in kept)
    return [f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,"
            f"fps={FPS},format=yuv420p,setsar=1[bc]"]


def assert_cfr(meta):
    """
    n-based selection is only correct if the source really is one constant
    frame rate with the first frame at PTS 0.  Check it with ffprobe instead of
    assuming it from the container; a variable-rate screen recording would make
    frame indices disagree with seconds.
    """
    src = source_file(meta)
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_frames,duration,start_pts,"
                        "avg_frame_rate,r_frame_rate,time_base",
                        "-print_format", "json", src],
                       capture_output=True, text=True)
    st = json.loads(p.stdout)["streams"][0]
    nbf = int(st["nb_frames"])
    dur = float(st["duration"])
    ok = (st["r_frame_rate"] == f"{FPS}/1" and st["avg_frame_rate"] == f"{FPS}/1"
          and int(st["start_pts"]) == 0 and nbf == round(dur * FPS))
    if not ok:
        raise SystemExit(
            f"source is not CFR {FPS} from PTS 0 "
            f"(nb_frames={nbf}, duration={dur}, r={st['r_frame_rate']}, "
            f"avg={st['avg_frame_rate']}, start_pts={st['start_pts']}); "
            "frame-number selection would drift against seconds")
    print(f"source CFR check: {nbf} frames = {dur:.2f}s at {FPS} fps, start_pts 0")


def audio_filter(total, chain=None):
    """Filter chain for the pre-cut WAV, whose length is already exact."""
    if chain is None:
        chain = (f"highpass=f={_A.get('highpass', 70)},"
                 f"afftdn=nr={_A.get('denoise_nr', 11)}:nf={_A.get('denoise_nf', -32)},"
                 f"dynaudnorm=f={_A.get('dynaudnorm_f', 250)}:g={_A.get('dynaudnorm_g', 13)}"
                 f":p={_A.get('dynaudnorm_p', 0.45)}:m={_A.get('dynaudnorm_m', 2)},"
                 f"alimiter=limit={_A.get('limiter', 0.95)},"
                 f"afade=t=in:st=0:d=0.6,"
                 f"afade=t=out:st={max(total - 1.4, 0):.3f}:d=1.4")
    return [f"[1:a]{chain}[aout]"]


# ------------------------------------------------------------------- dashboard

# drawbox evaluates x/y/w/h once at filter init: `t` is not available there,
# so an animated width silently falls back to "full width". Progress is drawn
# as a few step segments gated by `enable`, which *is* evaluated per frame.
def dashboard_layout(topics):
    """Row height and label size that actually fit the plate."""
    fs = fit_fs([t["short"] for t in topics], FONT, LABEL_W, ROW_FS_WANT)
    # rows must stop short of the plate's rounded bottom corner, and when there
    # are few topics the leftover space is distributed instead of left as a gap
    room = (PANEL_Y + PANEL_H) - LIST_Y - max(RAIL_INSET * 2, ROW_CLEAR)
    row_h = min(max(ROW_H_WANT, room / max(len(topics), 1)), ROW_H_MAX)
    # keep the row text clear of its own progress bar
    fs = min(fs, int((row_h - ROW_BAR_H - 8) / 1.16))
    if row_h < ROW_H_WANT or fs < ROW_FS_WANT:
        print(f"dashboard: {len(topics)} topics -> row_h={row_h:.1f} "
              f"fontsize={fs} (wanted {ROW_H_WANT}/{ROW_FS_WANT})")
    return LABEL_X, LABEL_W, row_h, max(fs, 9)


def dashboard_filters(topics, total):
    """Filters drawn on top of the overlaid plate (the plate itself is not
    drawn here -- see make_plate.py and the overlay in content())."""
    f = []
    label_x, label_w, row_h, fs = dashboard_layout(topics)

    # overall progress rail down the plate's left edge
    f.append(f"drawbox=x={RAIL_X}:y={RAIL_Y}:w={GLOB_W}:h={RAIL_H}"
             f":color={TRACK}@0.9:t=fill:" + gate(None))
    seg = RAIL_H / GLOB_STEPS
    for k in range(1, GLOB_STEPS + 1):
        f.append(f"drawbox=x={RAIL_X}:y={RAIL_Y + seg * (k - 1):.1f}"
                 f":w={GLOB_W}:h={seg + 0.6:.2f}:color={ACCENT}@0.9:t=fill"
                 ":" + gate(f"gte(t,{total * k / GLOB_STEPS:.3f})"))

    # --- clock and heading.  The hairline between them and the list is baked
    # into the plate (make_plate.py draws it so it shares the plate's alpha and
    # rounded silhouette) and imported from there, so the rule can never drift
    # away from the text above it.
    clock_y, head_y = CLOCK_Y, HEAD_Y
    total_tc = fmt_tc(total)
    # The elapsed slot is reserved for the widest value the clock will ever
    # print, so the hairline between elapsed and total never shifts while the
    # seconds tick.
    div_x = label_x + text_w(total_tc, FONT, CLOCK_FS) + 8
    f.append(f"drawtext=fontfile={FONT}:text='{TC_EXPR}'"
             f":fontcolor={ACCENT}:fontsize={CLOCK_FS}:x={label_x}:y={clock_y}"
             f":{TEXT_EDGE}:" + gate(None))
    f.append(f"drawbox=x={div_x}:y={clock_y + 3}:w=1:h={CLOCK_FS - 6}"
             f":color={TXT_MUTE}@0.40:t=fill:" + gate(None))
    f.append(f"drawtext=fontfile={FONT_R}:fontcolor={TXT_CHIP}:fontsize={CLOCK_TOTAL_FS}"
             f":text='{esc(total_tc)}':x={div_x + CLOCK_GAP}"
             f":y={clock_y + ascent(FONT, CLOCK_FS) - ascent(FONT_R, CLOCK_TOTAL_FS)}"
             f":{TEXT_EDGE}:" + gate(None))
    f.append(f"drawtext=fontfile={FONT}:text='{esc(LIST_HEAD)}'"
             f":fontcolor={TXT_CHIP}:fontsize={HEAD_FS}:x={label_x}:y={head_y}"
             f":{TEXT_EDGE}:" + gate(None))

    # One row per topic, plain text: a dot marks the row you are on, a tick
    # marks a row you have finished, an upcoming row gets nothing but its own
    # progress bar.  (No highlight band and no per-row pill -- a table of
    # contents is something you read, not a list of buttons.)
    for i, t in enumerate(topics):
        s, e, y = t["start"], t["end"], LIST_Y + i * row_h
        cur = f"between(t,{s:.3f},{e:.3f})"
        dur = max(e - s, 0.001)
        f.append(f"drawbox=x={TICK_X + 2}:y={y + (row_h - MARKER_DOT) / 2:.1f}"
                 f":w={MARKER_DOT}:h={MARKER_DOT}:color={ACCENT}@0.95:t=fill"
                 ":" + gate(cur))
        f.append(f"drawtext=fontfile={TICK_FONT}:text='{esc(TICK_GLYPH)}'"
                 f":fontcolor={ACCENT}:fontsize={TICK_FS}:x={TICK_X}"
                 f":y={y + (row_h - TICK_FS * 1.25) / 2:.1f}:{TEXT_EDGE}:"
                 + gate(f"gte(t,{e:.3f})"))
        for text, color, font, g in (
                (t["short"], TXT_MUTE, FONT_R, f"lt(t,{s:.3f})"),
                (t["short"], TXT_MAIN, FONT, cur),
                (t["short"], TXT_CHIP, FONT_R, f"gte(t,{e:.3f})")):
            f.append(f"drawtext=fontfile={font}:text='{esc(text)}'"
                     f":fontcolor={color}:fontsize={fs}:x={label_x}"
                     f":y={y + (row_h - fs * 1.2) / 2:.1f}:{TEXT_EDGE}:" + gate(g))
        by = y + row_h - ROW_BAR_H - 3
        f.append(f"drawbox=x={label_x}:y={by:.1f}:w={label_w}:h={ROW_BAR_H}"
                 f":color={TRACK}@0.9:t=fill:" + gate(None))
        psegs = (label_w - 2) / STEPS
        for k in range(1, STEPS + 1):
            f.append(f"drawbox=x={label_x + 1 + psegs * (k - 1):.1f}:y={by:.1f}"
                     f":w={psegs + 0.6:.2f}:h={ROW_BAR_H}:color={ACCENT}@0.95:t=fill"
                     ":" + gate(f"gte(t,{s + dur * k / STEPS:.3f})"))
    return f


def run(cmd, log):
    with open(log, "w") as fh:
        p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if p.returncode:
        sys.exit(f"ffmpeg failed -> {log}\n" + open(log).read()[-3000:])


def source_file(meta):
    """source/<video_id>.mp4, so a new project only edits edit/topics.json."""
    vid = meta.get("video_id", "")
    for cand in (os.path.join(ROOT, "source", f"{vid}.mp4"),
                 os.path.join(ROOT, "source", "input.mp4")):
        if os.path.exists(cand):
            return cand
    sys.exit(f"no source video found for video_id={vid!r} "
             f"(expected source/{vid}.mp4)")


def audio_wav():
    """render/audio_cut.wav, built on demand from edit/cuts.json."""
    wav = os.path.join(R, "audio_cut.wav")
    cuts = os.path.join(ROOT, "edit/cuts.json")
    if not os.path.exists(wav) or os.path.getmtime(wav) < os.path.getmtime(cuts):
        print("audio_cut.wav is missing or older than cuts.json -- cutting")
        run([sys.executable, os.path.join(ROOT, "scripts/cut_audio.py")],
            os.path.join(ROOT, "logs_cut_audio.txt"))
    return wav


def plate_png():
    """render/panel_plate.png, rebuilt whenever the style changes."""
    style = os.path.join(ROOT, "edit/style.json")
    if not os.path.exists(PLATE) or os.path.getmtime(PLATE) < os.path.getmtime(style):
        print("panel_plate.png is missing or older than style.json -- drawing")
        run([sys.executable, os.path.join(ROOT, "scripts/make_plate.py")],
            os.path.join(ROOT, "logs_make_plate.txt"))
    return PLATE


def content(total_override=0.0, preset="veryfast", vaqp=20):
    cuts, top, meta = load()
    assert_cfr(meta)
    kept, topics, total = cuts["kept"], top["topics"], top["edited_duration"]
    if total_override:
        kept = [k for k in kept if k[0] < total_override]
        kept[-1] = [kept[-1][0], min(kept[-1][1], total_override)]
        total = sum(e - s for s, e in kept)
        topics = [dict(t) for t in topics if t["start"] < total]
        topics[-1]["end"] = total

    parts = cut_filter(kept)
    # The plate is one static RGBA PNG; overlay repeats it and its rounded
    # alpha silhouette cannot be expressed with drawbox. One enable expression
    # on the overlay hides the whole plate at once; the text drawn on top is
    # gated by the same windows in gate().
    ov_en = f":enable='{VIS}'" if VIS else ""
    parts.append("[2:v]format=yuva420p[plv]")
    parts.append(f"[bc][plv]overlay=x={PANEL_X}:y={PANEL_Y}"
                 f":eof_action=repeat:format=auto{ov_en}[ov]")
    parts.append("[ov]" + ",".join(dashboard_filters(topics, total)) + "[db]")
    parts.append(f"[db]fade=t=in:st=0:d={FADE_C_IN},"
                 f"fade=t=out:st={max(total - FADE_C_OUT, 0):.3f}:d={FADE_C_OUT}"
                 f",format=nv12,hwupload[vout]")
    parts += audio_filter(total)

    spath = os.path.join(R, "filter_content.txt")
    open(spath, "w", encoding="utf-8").write("\n;\n".join(parts) + "\n")
    print(f"graph: {len(parts)} chains, {len(kept)} segments, total={total:.1f}s"
          + (f", {VIS.count('between(')} visibility windows" if VIS else ""))

    wav = audio_wav()
    in2 = (["-t", f"{total:.3f}"] if total_override else []) + ["-i", wav]
    out = os.path.join(R, "content_test.mp4" if total_override else "content.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-stats",
         "-extra_hw_frames", str(EXTRA_HW), "-vaapi_device", VAAPI_DEVICE,
         "-i", source_file(meta)] + in2 + ["-i", plate_png()] +
        ["-filter_complex_script", spath,
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", VA_CODEC, "-global_quality", str(vaqp),
         "-pix_fmt", "yuv420p",
         "-g", str(GOP), "-keyint_min", str(FPS),
         "-c:a", "aac", "-b:a", _A.get("bitrate", "160k"),
         "-ar", str(_A.get("sample_rate", 48000)), "-ac", "2",
         "-movflags", "+faststart", out],
        os.path.join(ROOT, "logs_render_content.txt"))
    print("->", out)


def card(lines_v, dur, out, tail=""):
    p = os.path.join(R, os.path.basename(out) + ".filter.txt")
    vchain = ("[0:v]" + ",".join(lines_v + ["format=nv12", "hwupload"]) + "[v]")
    achain = (f"[1:a]atrim=0:{dur},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1.0,"
              f"afade=t=out:st={dur - 1.5}:d=1.5[a]")
    open(p, "w", encoding="utf-8").write("\n;\n".join([vchain, achain]) + "\n")
    run(["ffmpeg", "-y", "-v", "error",
         "-extra_hw_frames", str(EXTRA_HW), "-vaapi_device", VAAPI_DEVICE,
         "-f", "lavfi", "-i",
         f"color=c={CARD_BG}:s={W_CANVAS}x{H_CANVAS}:r={FPS}:d={dur}",
         "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={dur}",
         "-filter_complex_script", p, "-map", "[v]", "-map", "[a]",
         "-c:v", VA_CODEC, "-global_quality", str(VA_QP),
         "-pix_fmt", "yuv420p", "-g", str(GOP), "-keyint_min", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
         "-t", str(dur), "-shortest", out],
        os.path.join(R, os.path.basename(out) + ".log"))
    print("->", out)


def intro(meta):
    """Title card. The headline is measured and wrapped, never clipped."""
    d = INTRO_DUR
    fs = _C.get("title_fontsize", 52)
    while fs > 34 and len(wrap(meta["title"], FONT, fs, CARD_W, 2)) > 2:
        fs -= 2
    lines = wrap(meta["title"], FONT, fs, CARD_W, 2)
    step = int(fs * 1.22)
    y0 = 520
    v = [f"drawtext=fontfile={FONT}:text='{esc(meta['lesson'])}'"
         f":fontcolor={ACCENT}:fontsize={_C.get('lesson_fontsize', 42)}"
         f":x={CARD_X}:y=380",
         f"drawbox=x={CARD_X}:y=470:w={CARD_W}:h=4:color={ACCENT}@0.9:t=fill"]
    for i, ln in enumerate(lines):
        v.append(f"drawtext=fontfile={FONT}:text='{esc(ln)}'"
                 f":fontcolor={TXT_MAIN}:fontsize={fs}:x={CARD_X}:y={y0 + i * step}")
    meta_y = max(720, y0 + len(lines) * step + 30)
    v.append(f"drawtext=fontfile={FONT_R}:text='{esc(meta['channel'])}  ·  "
             f"Data Engineering':fontcolor={TXT_META}"
             f":fontsize={_C.get('meta_fontsize', 30)}:x={CARD_X}:y={meta_y}")
    v.append("fade=t=in:st=0:d=%.1f,fade=t=out:st=%.1f:d=%.1f"
             % (_T.get("intro_fade_in", 0.8), d - _T.get("intro_fade_out", 0.9),
                _T.get("intro_fade_out", 0.9)))
    print(f"intro: headline {fs}px in {len(lines)} line(s), "
          f"{max(text_w(l, FONT, fs) for l in lines):.0f}px of {CARD_W}px")
    card(v, d, os.path.join(R, "intro.mp4"))


def outro_layout(tops):
    """Which topics the outro card lists, at what size, at which y.

    Selection is the topic's own `"recap": true` flag (edit/topics.json), not an
    index list in style.json: when episode 1 lost a topic, its `recap_pick`
    [1,5,8,11,13,19,22] silently fell out of range and the card drew 6 of 7
    lines.  A flag cannot point at the wrong topic; at worst it is missing, and
    that is an error rather than a slightly shorter card.

    Returns (picks, fontsize, [y per line]); verify_output.py measures the same
    list, so the card it checks is the card that gets drawn.
    """
    picks = [t for t in tops if t.get("recap")]
    if not picks:
        raise SystemExit('no topic is marked "recap": true in edit/topics.json '
                         "-- the outro card would be empty")
    fs = RECAP_FS
    while fs > 18 and RECAP_Y0 + len(picks) * int(fs * RECAP_LINE_MULT) > RECAP_BOTTOM:
        fs -= 1
    ys = [RECAP_Y0 + k * int(fs * RECAP_LINE_MULT) for k in range(len(picks))]
    return picks, fs, ys


def outro(meta):
    """Recap card. 'выпуск', not 'урок': these are episodes of a course."""
    d = OUTRO_DUR
    picks, fs, ys = outro_layout(json.load(open(
        os.path.join(ROOT, "edit/topics_edited.json"), encoding="utf-8"))["topics"])
    head = _C.get("outro_heading", "Что разобрали в этом выпуске")
    hfs = _C.get("outro_heading_fontsize", 44)
    while hfs > 24 and text_w(head, FONT, hfs) > CARD_W:
        hfs -= 2
    v = [f"drawtext=fontfile={FONT}:text='{esc(head)}'"
         f":fontcolor={ACCENT}:fontsize={hfs}:x={RECAP_X}:y=170",
         f"drawbox=x={RECAP_X}:y={170 + hfs + 16}:w={CARD_W}:h=3:"
         f"color={ACCENT}@0.5:t=fill"]
    for t, y in zip(picks, ys):
        for ln in wrap(t["title"], FONT_R, fs, CARD_W - 60, 1):
            v.append(f"drawtext=fontfile={FONT_R}:text='·  {esc(ln)}'"
                     f":fontcolor={TXT_CARD}:fontsize={fs}:x={RECAP_X}:y={y}")
    y = ys[-1] + int(fs * RECAP_LINE_MULT) + 20
    v.append(f"drawtext=fontfile={FONT}:text='{esc(_C.get('outro_next', 'Продолжение следует'))}'"
             f":fontcolor={TXT_MAIN}:fontsize=38:x={RECAP_X}:y={y}")
    v.append(f"drawtext=fontfile={FONT_R}:text='{esc(meta.get('group', ''))}'"
             f":fontcolor={TXT_META}:fontsize={RECAP_FS}:x={RECAP_X}:y={y + 58}")
    v.append("fade=t=in:st=0:d=%.1f,fade=t=out:st=%.1f:d=%.1f"
             % (_T.get("outro_fade_in", 0.6), d - _T.get("outro_fade_out", 1.6),
                _T.get("outro_fade_out", 1.6)))
    print(f"outro: {len(picks)} recap lines at {fs}px, list ends y={y}")
    card(v, d, os.path.join(R, "outro.mp4"))


def concat():
    lst = os.path.join(R, "concat.txt")
    open(lst, "w").write("file 'intro.mp4'\nfile 'content.mp4'\nfile 'outro.mp4'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", "-movflags", "+faststart", os.path.join(R, "final.mp4")],
        os.path.join(ROOT, "logs_concat.txt"))
    print("->", os.path.join(R, "final.mp4"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=float, default=0)
    ap.add_argument("--only", default="content,intro,outro,concat")
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--vaqp", type=int, default=20,
                    help="h264_vaapi global quality (lower = better)")
    a = ap.parse_args()
    _, top, meta = load()
    only = set(x.strip() for x in a.only.split(","))
    if "content" in only:
        content(a.test, a.preset, a.vaqp)
    if "intro" in only:
        intro(meta)
    if "outro" in only:
        outro(meta)
    if "concat" in only and not a.test:
        concat()


if __name__ == "__main__":
    main()
