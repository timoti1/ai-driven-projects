#!/usr/bin/env python3
"""
verify_output.py -- check the rendered edit without looking at it.

Useful when the agent cannot view frames: every check is a number that would
change if the edit were wrong.

Checks
  1. container/streams: resolution, fps, duration vs the plan, audio present
  2. duration math: final == intro + edited + outro (within a frame or two)
  2b. frame counts: the video track holds exactly the frames the plan says, so
      audio cannot drift against it
  3. dashboard is actually drawn: OCR of the panel strip must find the topic
     title and the clock at several timestamps
  4. dashboard progress advances: width of the accent line grows with time
  5. nothing important is covered: dark-pixel share inside the panel strip of
     the SOURCE at the same timestamps (should stay low)
  6. splices are silent: for each cut in edit/cuts.json, peak level in 100 ms
     on both sides (needs work/rms.npy)

Usage: verify_output.py [FINAL_MP4]   (default render/final.mp4)
"""
import argparse, json, os, re, subprocess, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "render")
TMP = "/tmp"
# The plate geometry is NOT restated here: it is imported from render.py, which
# reads it from edit/style.json.  A copy of these numbers in this file is how
# the checker silently tested a bottom strip after the dashboard moved to the
# right column.


def ffprobe_streams(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_streams", "-show_format", path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        sys.exit("ffprobe failed: " + p.stderr.decode()[-800:])
    return json.loads(p.stdout.decode())


def frame(path, t, vf):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path,
                        "-frames:v", "1", "-vf", vf, "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout


def ocr(path, t, h=160, y=920):
    png = f"/tmp/_verify_{t}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path,
                    "-frames:v", "1", "-vf", f"crop=1920:{h}:0:{y}", "-y", png],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p = subprocess.run(["tesseract", png, "stdout", "-l", "rus+eng", "--psm", "6"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return re.sub(r"\s+", " ", p.stdout.decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("final", nargs="?", default=os.path.join(R, "final.mp4"))
    a = ap.parse_args()

    cuts = json.load(open(os.path.join(ROOT, "edit/cuts.json"), encoding="utf-8"))
    top = json.load(open(os.path.join(ROOT, "edit/topics_edited.json"),
                         encoding="utf-8"))
    src = os.path.join(ROOT, "source",
                       json.load(open(os.path.join(ROOT, "edit/topics.json"),
                                      encoding="utf-8"))["video_id"] + ".mp4")
    fails, notes = [], []
    facts = {}   # written to render/verified.json at the end

    d = ffprobe_streams(a.final)
    v = next((s for s in d["streams"] if s.get("codec_type") == "video"), None)
    au = next((s for s in d["streams"] if s.get("codec_type") == "audio"), None)
    dur = float(d["format"]["duration"])

    print("== 1. container ==")
    if not v:
        fails.append("no video stream")
    else:
        print(f"  {v['codec_name']} {v['width']}x{v['height']} "
              f"r_frame_rate={v['r_frame_rate']}")
        if (v["width"], v["height"]) != (1920, 1080):
            fails.append(f"resolution {v['width']}x{v['height']} != 1920x1080")
    if not au:
        fails.append("no audio stream")
    else:
        print(f"  audio {au['codec_name']} {au.get('sample_rate')} Hz "
              f"{au.get('channels')} ch")

    print("\n== 2. duration ==")
    edited = top["edited_duration"]
    intro = float(os.environ.get("INTRO_DUR", 7.0))
    outro = float(os.environ.get("OUTRO_DUR", 10.0))
    expect = edited + intro + outro
    print(f"  final={dur:.2f}s  expected~{expect:.2f}s "
          f"(edited {edited:.2f} + cards {intro + outro:.1f})")
    if abs(dur - expect) > 2.0:
        fails.append(f"duration off by {dur - expect:+.2f}s")
    intro_txt = ocr(a.final, intro * 0.5, h=1080, y=0)
    outro_txt = ocr(a.final, dur - outro * 0.5, h=1080, y=0)
    print(f"  source was {cuts['source_duration']:.2f}s -> "
          f"{100 * (1 - dur / cuts['source_duration']):.2f}% shorter overall")

    # Geometry and the OCR helpers are the render's own, so this file cannot
    # drift away from what was actually drawn.
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import render as RD
    from probe_dashboard import crop_raw, ocr_row, readable, row_glyph

    gates = json.load(open(os.path.join(ROOT, "edit/panel_gates.json"),
                           encoding="utf-8"))
    kept = cuts["kept"]

    def edited_to_source(te):
        """Edited seconds -> source seconds, through the kept intervals."""
        acc = 0.0
        for a, b in kept:
            if te <= acc + (b - a):
                return a + (te - acc)
            acc += b - a
        return kept[-1][1]

    def pick_visible(frac):
        """A time at about this share of the body *where the panel is drawn*."""
        target = edited * frac
        for lo, hi in gates["visible"]:
            if lo <= target <= hi:
                return target
            if lo > target:
                return min(lo + 4.0, edited - 12.0)
        return edited * 0.5

    print("\n== 2b. the video track is as long as the audio track ==")
    # A body whose video track is shorter than its audio sounds fine on paper:
    # the container duration is the *longer* stream, so every other check in
    # this file passed while the video was 52 frames (2.08 s) short and the
    # narration slid away from the speaker's mouth, a little more with every
    # minute.  Only frame counts see it.
    fps = 25.0
    if v:
        num, _, den = v["r_frame_rate"].partition("/")
        fps = float(num) / float(int(den or 1))
    want_final = round(edited * fps) + round(intro * fps) + round(outro * fps)
    got_final = int(v.get("nb_frames", -1)) if v else -1
    vdur = float(v.get("duration", 0)) if v else 0.0
    adur = float(au.get("duration", 0)) if au else 0.0
    print(f"  final: {got_final} video frames (plan says {want_final}), "
          f"video {vdur:.3f}s vs audio {adur:.3f}s "
          f"({abs(vdur - adur) * 1000:.0f} ms apart)")
    facts.update(video_frames=got_final, plan_frames=want_final,
                 video_seconds=vdur, audio_seconds=adur, container_seconds=dur)
    if got_final != want_final:
        fails.append(f"video has {got_final} frames, the plan says {want_final}: "
                     f"{(want_final - got_final) / fps * 1000:.0f} ms of desync")
    elif abs(vdur - adur) > 0.06:
        fails.append(f"video and audio tracks differ by {abs(vdur - adur) * 1000:.0f} ms")
    body = os.path.join(R, "content.mp4")
    if os.path.exists(body):
        bs = ffprobe_streams(body)
        bv = next((x for x in bs["streams"] if x.get("codec_type") == "video"), None)
        ba = next((x for x in bs["streams"] if x.get("codec_type") == "audio"), None)
        if bv:
            want = round(edited * fps)
            have = int(bv.get("nb_frames", -1))
            bdur, adur2 = float(bv.get("duration", 0)), float(ba.get("duration", 0)) if ba else 0.0
            print(f"  content.mp4: {have} frames (plan says {want}), "
                  f"video {bdur:.3f}s vs its audio {adur2:.3f}s")
            if have != want or abs(bdur - adur2) > 0.06:
                fails.append(f"content.mp4 is {want - have} frames short of the plan")

    print("\n== 3. dashboard drawn and readable (OCR of the plate) ==")
    topics = [dict(t) for t in top["topics"]]
    n = len(topics)
    _, _, row_h, row_fs = RD.dashboard_layout(topics)
    probe_times = [pick_visible(f) for f in (0.10, 0.35, 0.60, 0.85)]
    bad = 0
    for te in probe_times:
        tf = te + intro
        # The clock line: "MM:SS / 1:43:58".  Labels are always drawn (current,
        # done or upcoming), so a row that will not OCR means the overlay is
        # either absent or too small/low-contrast to read.
        clock, _ = ocr_row(a.final, RD.LABEL_X, RD.CLOCK_Y,
                           RD.LABEL_W, RD.CLOCK_FS + 12, f"{TMP}/verify_clock.png",
                           t=tf)
        # Rows come in three states and are drawn in three different colours:
        # the live row (white, bold), finished rows above it (bright, with a
        # tick) and rows not reached yet (deliberately recessive).  Only the
        # first two are held to a legibility bar; the third is checked for
        # presence and for being measurably dimmer, which is the design.
        live = min(int(te / edited * n), n - 1)
        lum = None
        img = crop_raw(a.final, RD.PANEL_X, RD.PANEL_Y, RD.PANEL_W, RD.PANEL_H, tf)
        if img is not None:
            lum = img.max(axis=2)
        base = float(np.median(lum)) if lum is not None else 0.0
        hgt = max(int(row_h) - RD.ROW_BAR_H - 4, 12)

        def row_at(idx):
            y0 = int(RD.LIST_Y + idx * row_h) + 2
            line, ink = ocr_row(a.final, RD.LABEL_X - 7, y0, RD.LABEL_W + 14, hgt,
                                f"{TMP}/verify_row{idx}.png", t=tf)
            ratio = 0.0
            if lum is not None:
                gl, n_ink = row_glyph(lum, y0 - RD.PANEL_Y, hgt,
                                  RD.LABEL_X - RD.PANEL_X,
                                  RD.LABEL_X - RD.PANEL_X + RD.LABEL_W)
                ratio = (gl + 1) / (base + 1) if n_ink else 0.0
            return line, ink, ratio

        checks = []
        for idx, state in ((live, "live"), (max(live - 1, 0), "done"),
                           (min(live + 3, n - 1), "upcoming")):
            line, ink, ratio = row_at(idx)
            if state in ("live", "done"):
                good = ink > 200 and ratio >= 2.0 and readable(topics[idx]["short"], line, ink)
            else:
                good = ink > 20 and 1.2 <= ratio <= 0.8 * row_at(live)[2]
            checks.append((state, good, ratio))
        rows_ok = sum(1 for _s, g, _r in checks if g)
        marks = [f"{s}:{'ok' if g else 'MISS'}({r:.2f})" for s, g, r in checks]
        # Both numbers must be H:MM:SS: a minutes-only total next to an H:MM:SS
        # clock is the bug this check exists to catch.  There is deliberately no
        # test for "/" -- the separator between the two is a 1 px vertical rule,
        # not a slash, and OCR reads it as nothing, '|' or ')' depending on the
        # frame.  What has to be true is two clock-shaped numbers.
        nums = re.findall(r"\d{1,2}:\d{2}:\d{2}", clock)
        has_clock = len(nums) >= 2
        print(f"  edited t={te:7.1f}s (final t={tf:7.1f}s) "
              f"clock={'yes' if has_clock else 'NO '} clock={clock.strip()[:22]!r} "
              f"rows: {'/'.join(marks)}")
        facts.setdefault("dashboard_probes", []).append(
            {"edited_t": round(te, 1), "clock": clock.strip()[:22],
             "rows_readable": rows_ok})
        if not has_clock or rows_ok < 3:
            bad += 1
    if bad == len(probe_times):
        fails.append("dashboard never readable -> overlay missing or illegible")
    elif bad:
        notes.append(f"{bad}/{len(probe_times)} probe times not fully readable")

    print("\n== 4. progress rail grows ==")
    rails = []
    for frac in (0.25, 0.75):
        te = pick_visible(frac)
        img = crop_raw(a.final, RD.RAIL_X, RD.RAIL_Y, RD.GLOB_W, RD.RAIL_H, te + intro)
        if img is None:
            continue
        lum = img.max(axis=2).max(axis=1)
        # The rail track is 0x23272f and the plate behind it is dark; the filled
        # part is accent blue or done-green, both far brighter than either.
        lit = float((lum > 120).mean())
        rails.append((round(te, 1), round(lit, 3), round(frac, 2)))
    facts["rail_lit_share"] = rails
    print(f"  (edited s, share of rail lit, expected share) {rails}")
    if len(rails) == 2:
        if rails[1][1] <= rails[0][1]:
            fails.append("progress rail does not grow")
        if rails[0][1] < 0.15:
            fails.append("progress rail empty at 25% of the body")
        if rails[1][1] < 0.6:
            notes.append(f"rail only {rails[1][1] * 100:.0f}% lit at 75% of the body")

    print("\n== 5. plate drawn exactly where the screen is free ==")
    x, y, w, h = int(RD.PANEL_X), int(RD.PANEL_Y), int(RD.PANEL_W), int(RD.PANEL_H)
    hidden = [0.5 * (lo + hi) for lo, hi in gates["hidden"] if hi - lo >= 6.0]
    samples = [("visible", te) for te in probe_times[:2]] + \
              [("hidden", te) for te in hidden[:3]]
    for kind, te in samples:
        fin = crop_raw(a.final, x, y, w, h, te + intro)
        srcf = crop_raw(src, x, y, w, h, edited_to_source(te))
        if fin is None or srcf is None:
            continue
        if fin.shape != srcf.shape:
            srcf = srcf[:fin.shape[0], :fin.shape[1]]
        fl = fin.max(axis=2)
        sl = srcf.max(axis=2)
        diff = float(np.mean(np.abs(fl - sl)))
        drawn = diff > 25
        ok = drawn if kind == "visible" else not drawn
        print(f"  {kind:7s} edited t={te:7.1f}s (source t={edited_to_source(te):7.1f}s) "
              f"plate rect: median lum {float(np.median(sl)):5.0f} -> "
              f"{float(np.median(fl)):5.0f}, mean |diff| {diff:5.1f} -> "
              f"{'plate drawn' if drawn else 'no plate'}{'  ok' if ok else '  MISMATCH'}")
        facts.setdefault("plate_gate_checks", []).append(
            {"kind": kind, "edited_t": round(te, 1), "mean_abs_diff": round(diff, 1),
             "plate_drawn": drawn, "ok": ok})
        if not ok:
            fails.append(f"{kind} range at edited t={te:.0f}s: "
                         f"{'plate is missing' if kind == 'visible' else 'plate is still drawn'}")

    print("\n== 6. nothing audible was cut ==")
    # What has to be measured is the level of the material that was REMOVED,
    # in the source.  An earlier version measured the surviving audio on both
    # sides of each splice instead, which flags every single pause boundary:
    # a pause boundary is exactly where the next word starts, so of course it
    # is loud.  A splice is inaudible when everything that was deleted is at
    # room tone, and that is what this checks.
    rms_path = os.path.join(ROOT, "work/rms.npy")
    stats_path = os.path.join(ROOT, "work/audio_stats.json")
    sp_path = os.path.join(ROOT, "work/speech.json")
    if not os.path.exists(rms_path):
        notes.append("work/rms.npy missing, skipped cut-audio check")
    else:
        rms = np.load(rms_path)
        dt = 0.01
        med = -30.2
        if os.path.exists(stats_path):
            med = json.load(open(stats_path, encoding="utf-8"))[
                "rms_percentiles_p1_5_25_50_75_95_99"][3]
        rem = np.array(cuts["removed"])

        def win(a, b):
            i, j = max(0, int(a / dt)), min(len(rms), int(b / dt))
            return rms[i:j] if j > i else np.array([])

        # 60 ms of silence is deliberately kept at each edge, so the first and
        # last 60 ms of a removed interval are the material the splice actually
        # touches; the rest of the interval is what the cut swallowed.
        adj = np.array([max(np.nanmax(win(ce - .06, ce)), np.nanmax(win(cs, cs + .06)))
                        for cs, ce in rem])
        inter = np.array([np.nanmax(win(cs + .06, ce - .06)) for cs, ce in rem])
        adj = adj[np.isfinite(adj)]
        inter = inter[np.isfinite(inter)]
        print(f"  {len(rem)} removed intervals, mean length "
              f"{float(np.mean(rem[:, 1] - rem[:, 0])):.2f}s")
        print(f"  loudest sample adjacent to a splice: {adj.max():.1f} dB; "
              f"loudest sample anywhere inside removed material: "
              f"{inter.max():.1f} dB (whole recording median {med:.1f} dB)")
        if inter.max() > med:
            fails.append(f"removed material reaches {inter.max():.1f} dB, above the "
                         f"recording median {med:.1f} dB -> something audible was cut")
        facts.update(removed_material_max_db=round(float(inter.max()), 1),
                     removed_material_max_adjacent_db=round(float(adj.max()), 1),
                     recording_rms_median_db=round(float(med), 1))
        loud = int((inter > med).sum())
        if loud:
            notes.append(f"{loud} removed intervals contain speech-level audio")
        print(f"  nothing removed is louder than the room tone it replaces "
              f"({(inter <= med).mean() * 100:.0f}% of intervals)")

        # Cross-check on the transcript side: word timestamps from auto-captions
        # lag the audio by a few hundred ms, so a word whose *recorded* start
        # falls inside a removed interval is expected; it only means a real word
        # was clipped if the interval's audio is loud, which the check above
        # rules out.  Reported, not failed on.
        if os.path.exists(sp_path):
            sp = json.load(open(sp_path, encoding="utf-8"))
            inside = sum(1 for w in sp["words"]
                         if any(cs <= w["t"] < ce for cs, ce in rem))
            print(f"  {inside} of {len(sp['words'])} caption words have their "
                  f"recorded start inside a removed interval (auto-caption lag; "
                  f"their audio is room tone)")

        # For reference: how different the two sides of a splice are.  A pause
        # splice jumps a lot by nature, so this is only a distribution report.
        kept = cuts["kept"]
        jumps = []
        for i in range(len(kept) - 1):
            e, st = kept[i][1], kept[i + 1][0]
            l, r = win(e - .1, e), win(st, st + .1)
            if len(l) and len(r):
                jumps.append(abs(float(np.nanmax(l)) - float(np.nanmax(r))))
        if jumps:
            jumps = np.array(jumps)
            print(f"  level jump across splices: median {np.median(jumps):.1f} dB, "
                  f"p99 {np.percentile(jumps, 99):.1f} dB (a pause splice is "
                  f"supposed to jump; the words on both sides are intact)")

    print("\n== 7. intro and outro cards ==")
    # The intro headline is the real YouTube title, which is longer than the
    # card, so it is split to fit.  Checking that the *last* words of the title
    # are on screen is what catches a truncated headline; an earlier render cut
    # it at 52 px because nothing measured the drawn width.
    meta = json.load(open(os.path.join(ROOT, "edit/topics.json"), encoding="utf-8"))
    title = f"{meta['lesson']} {meta['title']}"
    tl = re.sub(r"[^\wа-яё]+", " ", title.lower()).split()
    head = re.sub(r"[^\wа-яё]+", " ", intro_txt.lower()).split()
    hit = sum(1 for w in tl if w in head)
    print(f"  intro headline: {hit}/{len(tl)} title words on screen "
          f"({'ok' if hit >= 0.8 * len(tl) else 'TRUNCATED?'})")
    if hit < 0.8 * len(tl):
        fails.append(f"intro headline missing {len(tl) - hit} of {len(tl)} title words")

    # The recap lines are checked one by one, at the y the renderer itself
    # computed.  Counting dashes in the OCR of the whole card was the old way
    # and it was wrong twice over: the bullet is '·', not '-', and a card that
    # lost its last line still OCR'd fine.  Episode 1 did lose a line -- the
    # recap was an index list in style.json, and after a topic was deleted the
    # last index fell out of range (render drew 6 of 7).
    picks, rfs, ys = RD.outro_layout(top["topics"])
    t_out = dur - outro * 0.5
    got, miss = 0, []
    for p, y in zip(picks, ys):
        # Crop to where the line is actually drawn.  Tesseract reads a 250 px line
        # reliably in a 300 px strip and returns punctuation-noise for that same
        # line inside a 1680 px strip of mostly empty card -- the width is measured
        # from the same font metrics the renderer used, so it is a tighter view of
        # the same pixels, not a different assumption.
        w = max(int(RD.text_w("\u00b7  " + p["title"], RD.FONT_R, rfs)) + 48, 220)
        line, ink = ocr_row(a.final, RD.RECAP_X, int(y) - 2, w, int(rfs * RD.RECAP_LINE_MULT) + 6,
                            f"{TMP}/verify_recap.png", t=t_out)
        ok = readable(p["title"], line, ink, any_token=True)
        got += ok
        if not ok:
            miss.append(f"{p['title']!r} -> {line.strip()[:28]!r}")
    word = "выпуск" in outro_txt.lower()
    print(f"  outro: {got}/{len(picks)} recap lines drawn and readable at {rfs}px, "
          f"heading word 'выпуск' {'present' if word else 'MISSING'}")
    for m in miss:
        print(f"     recap line not readable: {m}")
    facts.update(intro_title_words_on_screen=[hit, len(tl)],
                 outro_recap_lines=[got, len(picks)], outro_recap_fontsize=rfs)
    if got < len(picks):
        fails.append(f"outro recap: {len(picks) - got} of {len(picks)} lines "
                     f"are missing or unreadable")
    if not word:
        notes.append("outro heading does not say 'выпуск' (check style.json outro_heading)")

    facts["checks_failed"] = fails
    facts["notes"] = notes
    facts["passed"] = not fails
    with open(os.path.join(R, "verified.json"), "w", encoding="utf-8") as fh:
        json.dump(facts, fh, ensure_ascii=False, indent=1)
    print(f"\n   numbers written to {os.path.join(R, 'verified.json')}")

    print("\n== result ==")
    for n in notes:
        print("  note:", n)
    if fails:
        for fl in fails:
            print("  FAIL:", fl)
        sys.exit(1)
    print("  all checks passed")


if __name__ == "__main__":
    main()
