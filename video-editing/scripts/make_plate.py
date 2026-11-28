#!/usr/bin/env python3
"""
make_plate.py -- draw the translucent plate the dashboard is written on.

ffmpeg cannot round the corners of a drawbox, and stacking drawboxes cannot
undo corners either (a box can only add colour, never remove it).  So the
plate is authored here as a single RGBA PNG with PIL and handed to render.py,
which overlays it once per frame:

  * rounded corners, drawn properly;
  * one alpha value for the whole plate, so the lecture stays visible behind
    the panel while the text on top of it stays fully opaque and crisp;
  * the visibility windows from edit/panel_gates.json then gate a *single*
    overlay filter instead of ~600 draw filters.

Everything about the plate comes from edit/style.json so the next episode
reuses the same look.  The PNG is static: it is decoded once and reused by
overlay's eof_action=repeat.

  python scripts/make_plate.py            # -> render/panel_plate.png
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rgb(hexcolor):
    h = hexcolor.replace("0x", "").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    st = json.load(open(os.path.join(ROOT, "edit/style.json"), encoding="utf-8"))
    d = st.get("dashboard", {})
    p = st.get("palette", {})

    w = d.get("panel_w", 320)
    h = d.get("panel_h", 896)
    radius = int(d.get("plate_radius", 22))
    alpha = d.get("plate_alpha", 0.78)
    border_alpha = d.get("plate_border_alpha", 0.85)
    border_w = int(d.get("plate_border_w", 2))
    out = a.out or os.path.join(ROOT, d.get("plate_png", "render/panel_plate.png"))

    fill = rgb(p.get("plate_bg", p.get("panel_bg", "0x10141b")))
    accent = rgb(p.get("accent", "0x39c6ff"))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius,
                         fill=fill + (int(round(255 * alpha)),),
                         outline=accent + (int(round(255 * border_alpha)),),
                         width=border_w)

    # A rule under the heading/clock block, baked into the plate so it shares
    # the plate's alpha and its rounded silhouette.  Its y comes from render.py,
    # which draws the text above it: computing the same line in two files is how
    # the rule and the text end up at different heights.
    rule_y = render.RULE_Y
    dr.line([(radius + 4, rule_y), (w - radius - 5, rule_y)],
            fill=accent + (int(round(255 * border_alpha * 0.45)),), width=1)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    opaque = (np.asarray(img)[:, :, 3] > 0).mean()
    print(f"plate {w}x{h} radius={radius} fill alpha={alpha:.2f} "
          f"border={border_w}px alpha={border_alpha:.2f}, rule at y={rule_y}")
    print(f"covered {opaque * 100:.1f}% of the bounding box "
          f"(rounded corners are transparent) -> {out}")


if __name__ == "__main__":
    main()
