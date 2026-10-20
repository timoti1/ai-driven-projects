#!/usr/bin/env python3
"""Append a model entry to a llama-swap config; preserves comments/format."""
import argparse
import datetime
import re
import shutil
import sys

KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def fail(msg):
    print("add_model.py: error: " + msg, file=sys.stderr)
    sys.exit(1)


def read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().split("\n")


def find_section(lines, key):
    """Return (start, end) of a top-level section; end is exclusive."""
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^%s:\s*(#.*)?$" % key, ln):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if ln.strip() and not ln[0].isspace() and not ln.lstrip().startswith("#"):
            return (start, j)
    return (start, len(lines))


def section_keys(lines, rng):
    keys = []
    for ln in lines[rng[0] + 1:rng[1]]:
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s", ln + " ")
        if m:
            keys.append(m.group(1))
    return keys


def find_macro(lines, rng, name):
    for ln in lines[rng[0] + 1:rng[1]]:
        m = re.match(r"^\s+['\"]?([a-zA-Z0-9_-]+)['\"]?:", ln)
        if m and m.group(1) == name:
            return True
    return False


def llama_ref(args, lines):
    if args.macro:
        return "${%s}" % args.macro
    if args.llama_server:
        return args.llama_server
    mrng = find_section(lines, "macros")
    if mrng:
        for cand in ("llama-server", "llama_server"):
            if find_macro(lines, mrng, cand):
                return "${%s}" % cand
    fail("no llama-server macro in config and no --llama-server PATH given")


def cmd_block(args, lines):
    """Return cmd continuation lines (already indented 6 spaces)."""
    if args.engine == "custom":
        if not args.cmd:
            fail("engine custom requires --cmd")
        import textwrap
        return ["      " + s for s in textwrap.wrap(args.cmd.strip(), width=100)]
    if args.engine == "strata":
        if not (args.python and args.serve_script and args.strata_config):
            fail("engine strata requires --python, --serve-script and --strata-config")
        return [
            "      %s %s" % (args.python, args.serve_script),
            "      --engine strata",
            "      --config %s" % args.strata_config,
            "      --port ${PORT}",
        ]
    ref = llama_ref(args, lines)
    if not args.gguf:
        fail("engine llama-cpp requires --gguf")
    out = ["      " + ref, "      --model %s" % args.gguf]
    if args.mmproj:
        out.append("      --mmproj %s" % args.mmproj)
    if args.device:
        out.append("      --device %s" % args.device)
    if args.backend != "cpu":
        out.append("      -ngl %d" % (args.ngl if args.ngl is not None else 99))
    out.append("      --ctx-size %d" % args.ctx)
    if args.parallel is not None:
        out.append("      --parallel %d" % args.parallel)
    if args.threads is not None:
        out.append("      --threads %d" % args.threads)
    if args.flash_attn:
        out.append("      --flash-attn on")
    out.append("      --jinja")
    out.append("      --host %s" % args.bind_host)
    out.append("      --port ${PORT}")
    if args.metrics:
        out.append("      --metrics")
    if args.extra:
        out.extend(["      " + s for s in args.extra.split()])
    return out


def build_model_lines(args, lines):
    b = ["  %s:" % args.name, "    name: %s" % args.name]
    if args.description:
        b.append("    description: %s" % quote(args.description))
    if args.context:
        b.append("    capabilities:")
        b.append("      context: %d" % args.context)
    b.append("    cmd: >-")
    b.extend(cmd_block(args, lines))
    if args.env:
        b.append("    env:")
        for e in args.env:
            b.append("    - %s" % e)
    b.append("    ttl: %d" % args.ttl)
    return b


def quote(text):
    if re.match(r"^[A-Za-z0-9 ()/:;=,_.-]+$", text):
        return text
    return "'%s'" % text.replace("'", "'\"'\"'")


def matrix_insert(lines, var, model):
    mrng = None
    matrix_line = None
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s+)matrix:\s*$", ln)
        if m:
            matrix_line = i
            indent = len(m.group(1))
            end = len(lines)
            for j in range(i + 1, len(lines)):
                ln2 = lines[j]
                if ln2.strip() and not ln2.lstrip().startswith("#") and len(ln2) - len(ln2.lstrip()) <= indent:
                    end = j
                    break
            mrng = (i, end)
            break
    if mrng is None:
        fail("no routing.router.settings.matrix section; add the matrix router manually or use --matrix-var only with matrix routing")
    var_line = None
    for j in range(mrng[0] + 1, mrng[1]):
        m = re.match(r"^(\s+)vars:\s*$", lines[j])
        if m:
            var_line = j
            var_indent = len(m.group(1))
            break
    entry_indent = var_indent + 2 if var_line else matrix_line_indent(mrng[0], lines) + 2
    entry = " " * entry_indent + "%s: %s" % (var, model)
    if var_line is None:
        ins_at = mrng[0] + 1
        block = [" " * (entry_indent - 2) + "vars:", entry]
    else:
        for j in range(var_line + 1, mrng[1]):
            m = re.match(r"^\s+([A-Za-z0-9_.-]+):", lines[j])
            if m and m.group(1) == var:
                print("add_model.py: matrix var '%s' already exists, skipped" % var, file=sys.stderr)
                return lines
        ins_at = var_line + 1
        block = [entry]
    return lines[:ins_at] + block + lines[ins_at:]


def matrix_line_indent(i, lines):
    m = re.match(r"^(\s+)", lines[i])
    return len(m.group(1))


def main():
    p = argparse.ArgumentParser(description="add a model to a llama-swap config")
    p.add_argument("config")
    p.add_argument("--name", required=False)
    p.add_argument("--engine", choices=["llama-cpp", "strata", "custom"], default="llama-cpp")
    p.add_argument("--gguf")
    p.add_argument("--mmproj")
    p.add_argument("--backend", choices=["cpu", "vulkan", "cuda", "hip"], default="cpu")
    p.add_argument("--device")
    p.add_argument("--llama-server")
    p.add_argument("--macro")
    p.add_argument("--ctx", type=int, default=8192)
    p.add_argument("--ngl", type=int)
    p.add_argument("--ttl", type=int, default=900)
    p.add_argument("--parallel", type=int)
    p.add_argument("--threads", type=int)
    p.add_argument("--context", type=int)
    p.add_argument("--flash-attn", dest="flash_attn", action="store_true")
    p.add_argument("--metrics", action="store_true")
    p.add_argument("--bind-host", dest="bind_host", default="127.0.0.1")
    p.add_argument("--extra", default="")
    p.add_argument("--env", action="append", default=[])
    p.add_argument("--description", default="")
    p.add_argument("--python")
    p.add_argument("--serve-script")
    p.add_argument("--strata-config")
    p.add_argument("--cmd")
    p.add_argument("--matrix-var")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--list", dest="list_models", action="store_true")
    args = p.parse_args()

    lines = read_lines(args.config)

    if args.list_models:
        rng = find_section(lines, "models")
        for k in section_keys(lines, rng) if rng else []:
            print(k)
        return

    if not args.name or not KEY_RE.match(args.name):
        fail("--name is required and must match [A-Za-z0-9_.-]+")

    rng = find_section(lines, "models")
    if rng and args.name in section_keys(lines, rng):
        fail("model '%s' already exists in %s" % (args.name, args.config))

    block = build_model_lines(args, lines)
    for ln in block:
        print(ln)

    if args.dry_run:
        return

    if rng:
        lines = lines[:rng[1]] + [""] + block + lines[rng[1]:]
    else:
        lines = lines + ["", "models:"] + block

    if args.matrix_var:
        lines = matrix_insert(lines, args.matrix_var, args.name)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(args.config, "%s.bak-addmodel-%s" % (args.config, stamp))
    with open(args.config, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("added model '%s' to %s" % (args.name, args.config), file=sys.stderr)


if __name__ == "__main__":
    main()
