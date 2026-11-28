#!/usr/bin/env python3
"""
probe_dashboard.py -- measure the dashboard's look without rendering the video.

The agent cannot look at pictures, so "does the panel read well?" has to be
answered with numbers.  This renders the *real* dashboard (plate + rows +
progress + pills + clock, straight out of render.py and edit/style.json) over
4 s of test pattern and measures:

  ROUNDED CORNERS  encode the same frame with and without the plate overlay and
                   diff them; the plate-applied region must inset along an arc
                   near each corner (a profile is printed row by row).
  SEE-THROUGH      alpha is recovered per channel from
                   out = a*plate + (1-a)*background, sampled from a clean patch
                   of plate over a *flat* background.  Measuring this over a
                   busy background is unreliable -- the background varies per
                   pixel and the drawn elements pollute the estimate.
  LEGIBILITY       brightest glyph vs the local plate base (contrast ratio) on
                   both backgrounds, plus the per-row glyph/plate ratio, which is
                   what separates the three row states.
  OCR              tesseract must read the labels a viewer actually reads: the
                   live row and the finished rows above it.  Rows not reached yet
                   are drawn deliberately faint (they light up as the lecture gets
                   to them), so those are checked for ink, for a visibility floor
                   (palette.min_upcoming_contrast), and for being measurably
                   dimmer than a finished row -- not for legibility.
  FIT              no drawing may sit fully inside a rounded corner square.

Two backgrounds are used on purpose:
  canvas  color 0xf5f5f5, the measured mean of this channel's Paint canvas
          (243.8) -- the realistic case, and the one that decides acceptance;
  busy    testsrc2, loud and moving -- the worst case, reported only.

  python scripts/probe_dashboard.py
  python scripts/probe_dashboard.py --topics 5 --keep
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R          # noqa: E402

ROOT = R.ROOT
WORK = os.path.join(ROOT, "work")
CANVAS_RGB = (245, 245, 245)
BACKGROUNDS = {
    "canvas": "color=c=0xf5f5f5:s=1920x1080:r=25:d=4",
    "busy": "testsrc2=s=1920x1080:r=25:d=4",
}


def sh(cmd, **kw):
    text = kw.pop("text", False)
    return subprocess.run(cmd, capture_output=True, text=text, **kw)


def encode(src, script, out, plate=True):
    open(os.path.join(WORK, "probe_filter.txt"), "w", encoding="utf-8").write(script)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src]
    if plate:
        cmd += ["-i", R.plate_png()]
    cmd += ["-filter_complex_script", os.path.join(WORK, "probe_filter.txt"),
            "-map", "[o]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
            "-pix_fmt", "yuv420p", "-t", "4", "-an", out]
    p = sh(cmd, text=True)
    if p.returncode:
        raise SystemExit(f"probe encode failed:\n{p.stderr[-1200:]}")


def crop_raw(video, x, y, w, h, t=1.5):
    """
    Decode one rectangle of a probe frame as an (h, w, 3) float array.

    YUV 4:2:0 decode paths round an odd crop dimension **down** by a pixel, so an
    odd width or height makes the byte count disagree with the request.  Asking
    for even dimensions avoids that; a mismatch that still happens is an error and
    not a None, because every caller reads None as "there is nothing here" and an
    ink-less measurement is exactly what a broken crop looks like.
    """
    w, h = int(w), int(h)
    w += w % 2
    h += h % 2
    p = sh(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
            "-vf", f"crop={w}:{h}:{int(x)}:{int(y)}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    if not p.stdout:
        return None
    n = len(p.stdout)
    if n != w * h * 3:
        raise SystemExit(f"crop {w}x{h} at ({x},{y}) t={t} decoded {n} bytes, expected "
                         f"{w * h * 3} -- the probe would measure nothing and report "
                         f"'no ink' instead of a broken crop")
    return np.frombuffer(p.stdout, np.uint8).astype(float).reshape(h, w, 3)


def ocr_row(video, x, y, w, h, out_png, scale=4, margin=6, ink_lift=40, t=1.5):
    """
    OCR one row crop.

    tesseract reads dark ink on light paper and expects the page background to
    be the brightest thing in the picture.  A dashboard row is the opposite --
    light glyphs on a dark pill on a translucent plate -- and feeding the whole
    crop to it makes tesseract treat the *pill* as the page and the plate as a
    smudge, which is why short labels came back as '|'.

    So: find where the ink actually is, crop to that bounding box, upscale, and
    invert.  What tesseract then sees is a word on a white page, regardless of
    what the plate happens to be sitting on.
    """
    from PIL import Image
    img = crop_raw(video, x, y, w, h, t)
    if img is None:
        return "", 0
    lum = img.max(axis=2)
    base = float(np.median(lum))
    ink = lum > base + ink_lift
    n_ink = int(ink.sum())
    if n_ink < 20:
        return "", n_ink
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    y0 = max(rows[0] - margin, 0)
    y1 = min(rows[-1] + margin + 1, lum.shape[0])
    x0 = max(cols[0] - margin, 0)
    x1 = min(cols[-1] + margin + 1, lum.shape[1])
    band = lum[y0:y1, x0:x1]
    im = Image.fromarray(np.uint8(255 - band))
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    im.save(out_png)
    txt = sh(["tesseract", out_png, "-", "-l", "rus+eng", "--psm", "7"], text=True).stdout
    return txt, n_ink


def row_glyph(lum, y0, hgt, x0, x1, lift=12):
    """
    (mean luminance of the ink in one label band, ink pixel count).

    Rows are drawn in three different colours depending on their state, so the
    per-row measurement is what tells the probe whether a row was meant to be
    bright (current / done) or meant to be recessive (upcoming).  Ink is anything
    clearly above the plate's own level.
    """
    band = lum[int(y0):int(y0 + hgt), int(x0):int(x1)]
    base = float(np.median(lum))
    m = band > base + lift
    n_ink = int(m.sum())
    if not n_ink:
        return 0.0, 0
    # p75, not the mean: most ink pixels are anti-aliased edge pixels whose count
    # depends on how many thin letters the label has, so a mean makes a long label
    # look fainter than a short one at the same colour.  The 75th percentile sits
    # on the stroke bodies and compares colours honestly.
    return float(np.percentile(band[m], 75)), n_ink


def dilate(mask, size):
    """Binary dilation with a size x size square kernel (PIL, no scipy)."""
    from PIL import Image, ImageFilter
    img = Image.fromarray((mask * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MaxFilter(size))
    return np.asarray(img) > 127


def local_contrast(lum):
    """
    Contrast of the glyphs against the surface they are actually drawn on.

    The glyphs sit on their own dark pill, not on bare plate, and a viewer reads
    the glyph against that pill.  So: take bright pixels as the glyph mask, look
    at the neighbourhood, keep the pixels the pill darkened (clearly below the
    bare-plate median) and compare the glyph brightness with that.  Falling back
    to the plate median is what a style without pills would measure.
    """
    mask = lum > 200
    if not mask.any():
        return 0.0, 0.0
    glyph_lum = float(np.mean(lum[mask]))
    plate_med = float(np.median(lum))
    near = dilate(mask, 17) & ~dilate(mask, 3)
    pill = near & (lum < plate_med - 20)
    base = float(np.median(lum[pill])) if pill.any() else plate_med
    return glyph_lum, (glyph_lum + 1) / (base + 1)


# tesseract happily confuses Latin lookalikes for Cyrillic ones (c/C->с/С,
# a->а, e->е, o->о, p->р, x->х, T->Т, B->В, K->К, H->Н, M->М).  Folding both
# sides before comparing keeps the test about legibility instead of alphabet.
LOOKALIKE = str.maketrans("abcdehikmopxyTAHBMK", "аbсdehhikmopxyTAHBMK"[:19])
LOOKALIKE = str.maketrans({"a": "а", "c": "с", "e": "е", "o": "о", "p": "р",
                          "x": "х", "y": "у", "k": "к", "h": "н", "t": "т",
                          "A": "А", "B": "В", "C": "С", "D": "Д", "E": "Е",
                          "F": "Ф", "H": "Н", "K": "К", "M": "М", "N": "Н",
                          "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У"})


def fold(text):
    return alnum(text).translate(LOOKALIKE)


def readable(label, ocr_line, ink_px, min_ink=30, any_token=False):
    """
    Is this label readable in the OCR of its own row?

    Comparison is done on the longest whitespace-separated token of the label:
    tesseract mangles decorative bits (E · T · L, S1…Sn), so demanding the whole
    string would fail on things a person reads instantly.

    Labels that are only initials (E · T · L) have no long token and tesseract
    cannot reliably resolve three 15 px letters, so those are checked as "is
    there ink where the label should be" instead.
    """
    parts = [fold(p) for p in label.split() if fold(p)]
    if not parts:
        return True
    longest = max(parts, key=len)
    if len(longest) < 4:
        return ink_px >= min_ink
    if any_token:
        # A line of a long sentence (the outro recap) is a different problem from
        # a short label: tesseract at 26 px reads "Структурированные данные и БД"
        # as "Ир cash данные иБД" -- the line is plainly drawn and plainly
        # legible, but no single word is guaranteed to survive intact.  So: there
        # must be ink where the line should be, and at least one long word of it
        # must come back.  Panel rows keep the strict longest-token rule; they
        # are short enough for it.
        if ink_px < min_ink:
            return False
        hit = [p for p in parts if len(p) >= 5 and p in fold(ocr_line)]
        return bool(hit)
    return longest in fold(ocr_line)


def alnum(text):
    """Lowercase letters+digits only, for forgiving OCR comparison."""
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def frame(src, t):
    p = sh(["ffmpeg", "-v", "error", "-ss", str(t), "-i", src, "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    if not p.stdout:
        raise SystemExit("no frame decoded")
    return np.frombuffer(p.stdout, np.uint8).astype(float).reshape(1080, 1920, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", type=int, default=0,
                    help="how many rows to draw (default: all topics from the plan)")
    ap.add_argument("--keep", action="store_true", help="keep the probe videos")
    a = ap.parse_args()

    os.makedirs(WORK, exist_ok=True)
    _, ed, _ = R.load()
    topics = [dict(t) for t in ed["topics"]]
    if a.topics:
        topics = topics[:a.topics]
    n = len(topics)
    for i, t in enumerate(topics):                      # squeeze all rows into 4 s
        t["start"], t["end"] = 4.0 * i / n, 4.0 * (i + 1) / n
    dash = ",".join(R.dashboard_filters(topics, 4.0))

    X, Y, W, H = R.PANEL_X, R.PANEL_Y, R.PANEL_W, R.PANEL_H
    hexs = R._P.get("plate_bg", "0x10141b").replace("0x", "")
    plate_rgb = np.array([int(hexs[i:i + 2], 16) for i in (0, 2, 4)], float)
    want_alpha = float(R._D.get("plate_alpha", 0.72))
    radius = int(R._D.get("plate_radius", 22))

    print(f"plate {W}x{H} at x={X} y={Y}, {n} rows, authored alpha {want_alpha:.2f}, "
          f"radius {radius}, fill {hexs}")

    results = {}
    for name, src in BACKGROUNDS.items():
        on = (f"[0:v]fps=25,format=yuv420p[bc];[1:v]format=yuva420p[plv];"
              f"[bc][plv]overlay=x={X}:y={Y}:eof_action=repeat:format=auto[ov];"
              f"[ov]{dash}[db];[db]format=rgb24[o]")
        off = f"[0:v]fps=25,format=yuv420p[bc];[bc]{dash}[db];[db]format=rgb24[o]"
        m_on, m_off = f"{WORK}/probe_{name}_on.mp4", f"{WORK}/probe_{name}_off.mp4"
        encode(src, on, m_on)
        encode(src, off, m_off, plate=False)
        A, B = frame(m_on, 1.5), frame(m_off, 1.5)
        applied = (np.abs(A - B).max(axis=2))[Y:Y + H, X:X + W] > 12

        print(f"\n=== background: {name} ===")
        if name == "canvas":
            print(f"rounded corners (plate-applied x-span per row):")
            for dy in (1, 3, 6, 11, 16, 22, 60, H // 2, H - 22, H - 2):
                cols = np.where(applied[dy])[0]
                if not len(cols):
                    print(f"   row +{dy:3d}: nothing applied")
                    continue
                print(f"   row +{dy:3d}: x {int(cols.min()):3d}..{int(cols.max()):3d}"
                      f"  (inset {int(cols.min()):2d} left, {W - 1 - int(cols.max()):2d} right)")
            print(f"   {100 * (1 - applied.mean()):.2f}% of the footprint is untouched "
                  f"(that is the rounded corners)")
            # clean patch: top-right of the plate, above the first row and right of the clock
            patch = A[Y + 25:Y + 55, X + 250:X + 300]
            bg = np.array(CANVAS_RGB, float)
            est = ((bg - patch) / (bg - plate_rgb)).mean(axis=2)
            alpha = float(np.median(est))
            print(f"effective alpha from a clean patch: {alpha:.3f} "
                  f"(authored {want_alpha:.2f}) -> "
                  f"{100 * (1 - alpha):.0f}% of the canvas contrast still shows through")
        else:
            alpha = None

        lum = A[Y:Y + H, X:X + W].max(axis=2)
        plate_base = np.median(lum)
        glyphs, contrast = local_contrast(lum)
        # OCR row by row: one tesseract call per line.  Reading the whole column
        # in one pass makes tesseract merge rows and drop 15 px labels, which is
        # an artifact of the test rather than a property of the dashboard.
        _, _, row_h, _fs = R.dashboard_layout(topics)
        # The probe squeezes every topic into 4 s, so at t=1.5 the rows above the
        # live one are "done", the live one is "current", the rest are "upcoming"
        # -- and upcoming rows are deliberately dim.  Judging them by the same
        # legibility bar as the rows you actually read would be wrong: the design
        # says they recede until the lecture reaches them.
        live = min(int(1.5 / 4.0 * n), n - 1)
        min_up = float(R._P.get("min_upcoming_contrast", 1.35))
        missing, dim_bad, bright = [], [], []
        ocr_dim = 0
        for i, t in enumerate(topics):
            y0 = int(R.LIST_Y + i * row_h) + 2
            hgt = max(int(row_h) - R.ROW_BAR_H - 4, 12)
            png = f"{WORK}/probe_{name}_row{i}.png"
            sh(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", m_on, "-frames:v", "1",
                "-vf", f"crop={R.LABEL_W + 14}:{hgt}:{R.LABEL_X - 7}:{y0},"
                       f"scale=iw*3:ih*3:flags=lanczos,negate", png])
            # tesseract reads dark-on-light; the dashboard is light-on-dark,
            # so the row crop is inverted before OCR.
            line, ink_px = ocr_row(m_on, R.LABEL_X - 7, y0,
                                   R.LABEL_W + 14, hgt, png)
            gl, n_ink = row_glyph(lum, y0 - Y, hgt, R.LABEL_X - X,
                                      R.LABEL_X - X + R.LABEL_W)
            ratio = (gl + 1) / (plate_base + 1) if n_ink else 0.0
            state = "current" if i == live else ("done" if i < live else "upcoming")
            if state in ("current", "done"):
                bright.append(ratio)
                if not readable(t["short"], line, ink_px):
                    missing.append(f"{t['short']} [{state}] (ocr: {line.strip()[:32]!r})")
            else:
                if n_ink < 20:
                    dim_bad.append(f"{t['short']} has no ink at all")
                elif ratio < min_up:
                    dim_bad.append(f"{t['short']} too faint to find at all ({ratio:.2f}:1)")
                if readable(t["short"], line, ink_px):
                    ocr_dim += 1
            if not a.keep and os.path.exists(png):
                os.remove(png)
        n_done_cur = len(bright)
        n_up = n - n_done_cur
        med_bright = float(np.median(bright)) if bright else 0.0
        up_ratios = []
        for i, t in enumerate(topics):
            if i <= live:
                continue
            y0 = int(R.LIST_Y + i * row_h) + 2
            hgt = max(int(row_h) - R.ROW_BAR_H - 4, 12)
            gl, n_ink = row_glyph(lum, y0 - Y, hgt, R.LABEL_X - X,
                                      R.LABEL_X - X + R.LABEL_W)
            if n_ink:
                up_ratios.append((gl + 1) / (plate_base + 1))
        med_up = float(np.median(up_ratios)) if up_ratios else 0.0
        # the hierarchy has to be real, not declared: a finished row must read
        # clearly stronger than a row that has not been reached yet
        hierarchy = med_bright >= 2.0 and med_up <= 0.8 * med_bright
        print(f"plate base luminance {plate_base:.0f}/255, glyph luminance "
              f"{glyphs:.0f}/255 vs its own local background -> contrast {contrast:.2f}:1")
        print(f"row states at t=1.5 s: {live} done, 1 current, {n_up} upcoming")
        print(f"  glyph/plate contrast: current+done {med_bright:.2f}:1, "
              f"upcoming {med_up:.2f}:1  (hierarchy "
              f"{'ok' if hierarchy else 'BROKEN'}; upcoming floor {min_up:.2f}:1)")
        print(f"OCR of the rows you read (current + done): "
              f"{n_done_cur - len(missing)}/{n_done_cur} readable"
              + ("" if not missing else "\n   " + "\n   ".join(missing)))
        if dim_bad:
            print("   upcoming rows failing the visibility floor: " + "; ".join(dim_bad))
        print(f"  upcoming rows that OCR anyway at this faintness: {ocr_dim}/{n_up} (informational)")
        results[name] = dict(alpha=alpha, contrast=contrast, missing=missing,
                             dim_bad=dim_bad, hierarchy=hierarchy, med_up=med_up,
                             med_bright=med_bright)

    # nothing may be drawn fully inside a rounded corner square
    corners = [(slice(0, radius), slice(0, radius)), (slice(0, radius), slice(W - radius, W)),
               (slice(H - radius, H), slice(0, radius)), (slice(H - radius, H), slice(W - radius, W))]
    A = frame(f"{WORK}/probe_canvas_on.mp4", 1.5)
    B = frame(f"{WORK}/probe_canvas_off.mp4", 1.5)
    applied = (np.abs(A - B).max(axis=2))[Y:Y + H, X:X + W] > 12
    bad = sum(1 for s, c in corners if applied[s, c].mean() > 0.9)
    print(f"\nFIT: {bad}/4 rounded corner squares fully covered by drawing")

    c = results["canvas"]
    ok = (c["alpha"] is not None and abs(c["alpha"] - want_alpha) <= 0.05
          and c["contrast"] >= 4.0 and not c["missing"] and bad == 0
          and not c["dim_bad"] and c["hierarchy"]
          and 100 * (1 - applied.mean()) > 0.05)
    print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}"
          f"  (rounded corners, alpha within 0.05 of {want_alpha:.2f}, "
          f">=4:1 for the rows you read, upcoming rows dim but above the floor, "
          f"current/done labels OCR-readable, corners clear)")
    for f in sum([[f"{WORK}/probe_{k}_on.mp4", f"{WORK}/probe_{k}_off.mp4"]
                  for k in BACKGROUNDS], []):
        if a.keep:
            print("kept", f)
        elif os.path.exists(f):
            os.remove(f)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
