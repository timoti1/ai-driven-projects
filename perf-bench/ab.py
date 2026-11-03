#!/usr/bin/env python3
"""ab.py - interleaved A/B and contention probes for engine configurations.

  python ab.py ab    --spec ab.example.json --reps 3 --rounds 2 --gen 1024
  python ab.py probe --spec ab.example.json --reps 3 --gen 1024

`ab` alternates arms across rounds so thermal/drift cannot masquerade as a
config effect; `probe` measures the target with a competing workload idle and
then saturated. Arms and interference are shell templates in the spec file, so
the tool itself stays host- and engine-agnostic (see ab.example.json).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import ab, util  # noqa: E402


def main():
    p = argparse.ArgumentParser(prog="ab.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["ab", "probe"])
    p.add_argument("--spec", required=True, help="arms spec (see ab.example.json)")
    p.add_argument("--reps", type=int, default=3, help="repetitions per arm per round")
    p.add_argument("--rounds", type=int, default=2, help="A/B alternation rounds")
    p.add_argument("--gen", type=int, default=1024, help="generated tokens per decode rep")
    p.add_argument("--prompt-tokens", dest="prompt_tokens", type=int, default=8000)
    p.add_argument("--port", type=int, help="port the arms bind to (default from spec)")
    p.add_argument("--ready-timeout", dest="ready_timeout", type=int, help="seconds to wait for /health")
    p.add_argument("--timeout", type=int, default=1800, help="per-request timeout")
    p.add_argument("--out", help="results dir (default ./results)")
    p.add_argument("--tag", help="label for summary grouping")
    args = p.parse_args()
    return ab.run(args.spec, args)


if __name__ == "__main__":
    sys.exit(main())
