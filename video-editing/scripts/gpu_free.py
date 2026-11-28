#!/usr/bin/env python3
"""
gpu_free.py -- which /dev/dri/renderD* is free enough to render on.

The rendering host here runs llama-server on one of two GPUs and keeps ~54 GB of
system RAM, so two things have to be checked before a render is started: is the
encode card actually idle, and is there RAM left (see ENVIRONMENT.md -- a
12.7 GB ffmpeg graph once OOM-killed the render and a neighbour with it).

VRAM usage is read from sysfs, which needs no ROCm userspace and no root:

    /sys/class/drm/renderD128/device/mem_info_vram_used   (kB)
    /sys/class/drm/renderD128/device/mem_info_vram_total  (kB)
    /sys/class/drm/renderD128/device/uevent               -> PCI bus id

and the bus id is matched against /dev/dri/by-path so a card can be named
("Sapphire on renderD128") instead of guessed.  `rocm-smi --showbusid` prints the
same mapping if it is installed.

Usage:
  gpu_free.py                 # table + which node to pass to ffmpeg
  gpu_free.py --free          # print just the free node's path; exit 1 if none
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

# A 1080p VAAPI encode needs only a few hundred MB of VRAM, and h264_vaapi keeps
# working on a card that is full of models (GOTCHAS 8) -- what does not work there
# is vp9_vaapi, which fails with EINVAL.  So the question is not "is this card
# empty" but "which card has the most room", and how much room is left.
MIN_FREE_VRAM = 512 * 1024 * 1024
# A flat 1080p VAAPI graph peaks around 350 MB RSS, so the floor is low; it is
# not zero because this host runs llama-server at ~54 GB and a render that
# outgrows what is left gets OOM-killed, taking something else with it.
MIN_FREE_RAM_MB = 768     # refuse below this
WARN_FREE_RAM_MB = 2048   # warn below this


def read_bytes(path):
    """amdgpu reports VRAM counters in bytes; some drivers report kB.  The
    magnitude tells them apart (a card is never 1e10 kB)."""
    try:
        v = int(open(path).read().strip())
    except Exception:
        return None
    return v * 1024 if v < 10 ** 8 else v


def bus_id(dev_path):
    """renderD128 -> 'PCI:0000:06:00.0' via by-path, which encodes the bus id."""
    card = os.path.basename(dev_path)
    for p in glob.glob("/dev/dri/by-path/*-render"):
        if os.path.basename(os.path.realpath(p)) == card:
            m = re.search(r"pci-([0-9a-f:.]+)-", os.path.basename(p))
            if m:
                return m.group(1)
    ue = os.path.join("/sys/class/drm", card, "device", "uevent")
    try:
        for line in open(ue):
            if line.startswith("PCI_SLOT_NAME="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return "?"


def holders(dev_path):
    """Processes with the render node open, best effort (fuser may be absent)."""
    if not shutil.which("fuser"):
        return []
    out = subprocess.run(["fuser", dev_path], capture_output=True, text=True)
    pids = out.stdout.split()
    names = []
    for pid in pids:
        try:
            names.append(f"{pid}:{open(f'/proc/{pid}/comm').read().strip()}")
        except Exception:
            names.append(pid)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--free", action="store_true",
                    help="print only the path of a free render node, exit 1 if none")
    ap.add_argument("--ram", action="store_true", help="also report free system RAM")
    a = ap.parse_args()

    nodes = []
    for dev in sorted(glob.glob("/sys/class/drm/renderD*")):
        name = os.path.basename(dev)
        used, total = (read_bytes(os.path.join(dev, "device", "mem_info_vram_used")),
                       read_bytes(os.path.join(dev, "device", "mem_info_vram_total")))
        if total is None:
            continue            # a display-only node with no VRAM counters
        path = f"/dev/dri/{name}"
        used = used or 0
        nodes.append(dict(path=path, bus=bus_id(path), used=used, total=total,
                          room=total - used, who=holders(path)))
    nodes.sort(key=lambda n: -n["room"])
    for n in nodes:
        n["free"] = n["room"] >= MIN_FREE_VRAM

    if not nodes:
        print("no render nodes with VRAM counters found (is the GPU driver up?)",
              file=sys.stderr)
        sys.exit(2)

    mem = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        mem[k] = int(v.strip().split()[0])
    avail_mb = mem.get("MemAvailable", 0) / 1024

    if a.free:
        if nodes[0]["free"] and avail_mb >= MIN_FREE_RAM_MB:
            print(nodes[0]["path"])
            return
        print("no render node with enough VRAM and RAM headroom", file=sys.stderr)
        sys.exit(1)

    print(f"{'node':18s} {'PCI bus':16s} {'VRAM free':>16s}  room")
    for n in nodes:
        print(f"{n['path']:18s} {n['bus']:16s} "
              f"{n['room'] / 2**30:6.2f}/{n['total'] / 2**30:5.2f} GB  "
              f"{'enough' if n['free'] else 'too little'}")
    print("  (a card holding models is still fine for h264_vaapi; vp9_vaapi is the"
          " one that fails with EINVAL -- GOTCHAS 8)")
    print(f"system RAM available: {avail_mb / 1024:.1f} GB "
          f"({100 * avail_mb / mem['MemTotal']:.0f}% of {mem['MemTotal'] / 1048576:.1f} GB)"
          + ("   <-- too tight for a render" if avail_mb < MIN_FREE_RAM_MB
             else "   <-- little headroom; keep the graph flat (ENVIRONMENT.md)"
             if avail_mb < WARN_FREE_RAM_MB else ""))
    if nodes[0]["free"]:
        print(f"use: -vaapi_device {nodes[0]['path']}")
    else:
        print("no node has room left: encode with libx264 instead, or free a card")
    sys.exit(0 if nodes[0]["free"] and avail_mb >= MIN_FREE_RAM_MB else 1)


if __name__ == "__main__":
    main()
