#!/usr/bin/env python3
"""pi --mode json event stream -> human-readable progress lines (host side).
Aborts the run (docker kill) on a repetition loop or a dead stream."""
import json
import select
import subprocess
import sys
import time

LOOP_LIMIT = 10       # same tool command OR assistant text this many times in a row
IDLE_LIMIT = 15 * 60  # no stream event for this many seconds


def render(e):
    t = e.get("type")
    if t == "tool_execution_start":
        a = e.get("args") or {}
        detail = str(a.get("command") or a.get("path") or "")
        return f"-> {e.get('toolName')}: {detail}"
    if t == "message_end":
        m = e.get("message") or {}
        if m.get("role") == "assistant":
            txt = "".join(
                c.get("text", "") for c in m.get("content", [])
                if isinstance(c, dict) and c.get("type") == "text"
            )
            if txt.strip():
                return txt.strip()   # full text, newlines kept: one batch result per line
    if t == "tool_execution_end" and e.get("isError"):
        return f"!! {e.get('toolName')} failed"
    if t == "agent_end":
        return "=== agent finished ==="
    return None


def kill(name, reason, run_name=None, bench=None):
    print(f"!! {reason} — killing container {name}", flush=True)
    try:
        subprocess.run(["docker", "kill", name], timeout=30, capture_output=True)
    except Exception as ex:
        print(f"!! docker kill failed: {ex}", flush=True)
    if run_name and bench and reason.startswith("LOOP"):
        marker = os.path.join(".", "runs", run_name, f".loop_{bench}")
        try:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w") as f:
                f.write(reason + "\n")
        except Exception:
            pass


def main(name, run_name=None, bench=None):
    last_cmd = None
    last_text = None
    cmd_repeats = 0
    text_repeats = 0
    last_event = time.monotonic()
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 30)
        if not ready:
            if time.monotonic() - last_event > IDLE_LIMIT:
                kill(name, f"NO STREAM for {IDLE_LIMIT // 60}m")
                return 1
            continue
        line = sys.stdin.readline()
        if not line:
            break
        last_event = time.monotonic()
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "tool_execution_start":
            cmd = str((e.get("args") or {}).get("command", ""))
            if cmd == last_cmd:
                cmd_repeats += 1
            else:
                cmd_repeats = 1
                last_cmd = cmd
            if cmd_repeats >= LOOP_LIMIT:
                kill(name, f"LOOP: same command repeated {cmd_repeats}x: {cmd[:80]}", run_name, bench)
                return 1
            text_repeats = 0
        elif e.get("type") == "message_end" and (e.get("message") or {}).get("role") == "assistant":
            txt = "".join(
                c.get("text", "") for c in (e.get("message") or {}).get("content", [])
                if isinstance(c, dict) and c.get("type") == "text"
            ).strip()
            if txt:
                if txt == last_text:
                    text_repeats += 1
                else:
                    text_repeats = 1
                    last_text = txt
                if text_repeats >= LOOP_LIMIT:
                    kill(name, f"LOOP: same assistant text repeated {text_repeats}x", run_name, bench)
                    return 1
            else:
                text_repeats = 0
        out = render(e)
        if out:
            print(out, flush=True)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sample = [
            {"type": "tool_execution_start", "toolName": "bash", "args": {"command": "ls -la\npwd"}},
            {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "Reading batch 1."}]}},
            {"type": "tool_execution_end", "toolName": "bash", "isError": True},
            {"type": "agent_end"},
        ]
        lines = [render(e) for e in sample]
        assert lines == ["-> bash: ls -la\npwd", "Reading batch 1.", "!! bash failed", "=== agent finished ==="], lines
        print("selftest ok")
    else:
        args = sys.argv[1:]
        name = None
        run_name = None
        bench = None
        i = 0
        while i < len(args):
            if args[i] == "--name" and i + 1 < len(args):
                name = args[i + 1]
                i += 2
            elif args[i] == "--run-name" and i + 1 < len(args):
                run_name = args[i + 1]
                i += 2
            elif args[i] == "--bench" and i + 1 < len(args):
                bench = args[i + 1]
                i += 2
            else:
                i += 1
        sys.exit(main(name, run_name, bench))
