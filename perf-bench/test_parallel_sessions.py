#!/usr/bin/env python3
"""Test parallel sessions: send two concurrent requests to measure combined throughput."""

import json
import time
import urllib.request
import threading
import sys


def send_request(session_id, prompt_tokens, max_tokens, results, url="http://127.0.0.1:5800"):
    """Send a single completion request and measure timing."""
    # Build a prompt of approximately prompt_tokens characters
    prompt = "The quick brown fox jumps over the lazy dog. " * (prompt_tokens // 8 + 1)
    prompt = prompt[:prompt_tokens]

    payload = json.dumps({
        "model": "avalon-qwen3.8-flash-next-C2",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "top_k": 30,
        "top_p": 0.95,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        results[session_id] = {"error": str(e)}
        return

    elapsed = time.time() - start

    choice = data.get("choices", [{}])[0]
    usage = data.get("usage", {})
    timings = data.get("timings", {})

    results[session_id] = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "elapsed": elapsed,
        "prompt_per_second": timings.get("prompt_per_second", 0),
        "predicted_per_second": timings.get("predicted_per_second", 0),
        "first_token_s": timings.get("predicted_per_second", 0) and 0,  # not available in non-stream
        "finish_reason": choice.get("finish_reason", "unknown"),
    }


def main():
    # Test configuration
    prompt_tokens = 8192  # ~8K context
    max_tokens = 128

    print(f"=== Parallel Sessions Test ===")
    print(f"Prompt size: {prompt_tokens} tokens, Max tokens: {max_tokens}")
    print(f"URL: http://127.0.0.1:5800")
    print()

    # Test 1: Single session
    print("--- Test 1: Single session ---")
    results1 = {}
    send_request(1, prompt_tokens, max_tokens, results1)
    r1 = results1.get(1, {})
    print(f"  Session 1: {r1.get('completion_tokens', 0)} tokens in {r1.get('elapsed', 0):.2f}s")
    print(f"  Decode: {r1.get('predicted_per_second', 0):.1f} tps")
    print(f"  Prompt: {r1.get('prompt_tokens', 0)} tokens at {r1.get('prompt_per_second', 0):.1f} tps")
    single_decode_tps = r1.get('predicted_per_second', 0)
    single_prompt_tps = r1.get('prompt_per_second', 0)
    single_total_tokens = r1.get('total_tokens', 0)
    single_elapsed = r1.get('elapsed', 0)

    print()

    # Test 2: Two parallel sessions
    print("--- Test 2: Two parallel sessions (simultaneous) ---")
    results2 = {}
    threads = []
    start_all = time.time()

    for sid in [1, 2]:
        t = threading.Thread(target=send_request, args=(sid, prompt_tokens, max_tokens, results2))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_elapsed = time.time() - start_all

    r2a = results2.get(1, {})
    r2b = results2.get(2, {})

    total_completion = r2a.get('completion_tokens', 0) + r2b.get('completion_tokens', 0)
    total_prompt = r2a.get('prompt_tokens', 0) + r2b.get('prompt_tokens', 0)

    print(f"  Session 1: {r2a.get('completion_tokens', 0)} tokens in {r2a.get('elapsed', 0):.2f}s, decode={r2a.get('predicted_per_second', 0):.1f} tps")
    print(f"  Session 2: {r2b.get('completion_tokens', 0)} tokens in {r2b.get('elapsed', 0):.2f}s, decode={r2b.get('predicted_per_second', 0):.1f} tps")
    print(f"  Wall clock time: {total_elapsed:.2f}s")
    print(f"  Combined completion: {total_completion} tokens")
    print(f"  Combined decode throughput: {total_completion / total_elapsed:.1f} tps (wall clock)")
    print(f"  Combined prompt: {total_prompt} tokens")
    combined_prompt_tps = total_prompt / total_elapsed
    print(f"  Combined prompt throughput: {combined_prompt_tps:.1f} tps (wall clock)")

    print()
    print("=== COMPARISON ===")
    print(f"Single session decode:  {single_decode_tps:.1f} tps")
    print(f"Two parallel decode:    {total_completion / total_elapsed:.1f} tps (combined)")
    print(f"Ratio (combined/single): {(total_completion / total_elapsed) / single_decode_tps:.2f}x")
    print()
    print(f"Single session prompt:  {single_prompt_tps:.1f} tps")
    print(f"Two parallel prompt:    {combined_prompt_tps:.1f} tps (combined)")
    print(f"Ratio (combined/single): {combined_prompt_tps / single_prompt_tps:.2f}x")


if __name__ == "__main__":
    main()
