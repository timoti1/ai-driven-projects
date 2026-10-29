#!/usr/bin/env python3
# Runs on the llama-swap host (piped via ssh stdin): print the GGUF stem the model id in argv[1] loads.
# argv[2] = llama-swap config path; engine-wrapper models (cmd --config *.json) resolve through that JSON's args.
import json, os, re, sys

mid, cfg_path = sys.argv[1], sys.argv[2]

def stem(path):
    s = re.sub(r"\.gguf$", "", os.path.basename(path), flags=re.I)
    return re.sub(r"-\d{5}-of-\d{5}$", "", s)

def model_in_cmd(block):
    m = re.search(r"--model\s+(\S+\.gguf)", block, re.I)
    if m:
        return m.group(1)
    m = re.search(r"--config\s+(\S+\.json)", block)
    if m:
        try:
            args = json.load(open(m.group(1))).get("args", [])
        except Exception:
            return None
        for i, a in enumerate(args):
            if a in ("--native", "--model", "--gguf") and i + 1 < len(args):
                if args[i + 1].lower().endswith(".gguf"):
                    return args[i + 1]
    return None

text = open(cfg_path).read()
mo = re.search(rf"^  {re.escape(mid)}:\s*$(.*?)(?=^(?:  \S|\S)|\Z)", text, re.M | re.S)
if not mo:
    sys.exit(f"model '{mid}' not found in {cfg_path}")
path = model_in_cmd(mo.group(1))
if not path:
    sys.exit(f"no GGUF path in cmd of model '{mid}'")
print(stem(path))
