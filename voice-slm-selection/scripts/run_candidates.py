#!/usr/bin/env python3
"""Run cleanup+meaning tasks for each candidate endpoint over data/cases.json."""
import argparse, json, time, urllib.request

SYSTEM = (
    "Ты пост-обработчик голосового ввода. Полученный текст — расшифровка русской речи "
    "(возможны ошибки распознавания, опечатки, повторы, слова-паразиты, отсутствие "
    "пунктуации, англо-термины на слух). Верни ОДНУ очищенную версию: расставь знаки "
    "препинания, убери мусор, исправь явные ошибки распознавания, сохранив смысл. "
    "Ничего не добавляй и не комментируй. Если текст — инструкция, оставь инструкцией."
)


def post(url, model, messages, max_tokens=400, temperature=0.3):
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    t0 = time.time()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    dt = time.time() - t0
    txt = (d["choices"][0]["message"]["content"] or "").strip()
    u = d.get("usage") or {}
    n = u.get("completion_tokens") or 0
    return txt, dt, (n / dt if dt > 0 else 0)


def run(name, url, model, cases, max_tokens):
    rows = []
    for c in cases:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": c["raw"]}]
        try:
            txt, dt, tps = post(url, model, msgs, max_tokens)
        except Exception as e:
            txt, dt, tps = f"ERROR {e}", 0.0, 0.0
        rows.append({"id": c["id"], "raw": c["raw"], "gold_meaning": c["gold_meaning"],
                     "out": txt, "sec": round(dt, 2), "tps": round(tps, 2)})
        print(f"[{name}] {c['id']} {dt:5.1f}s {tps:5.1f} t/s  {txt[:110]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases.json")
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--model", default="local")
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    cases = json.load(open(a.cases))["cases"]
    rows = run(a.name, a.endpoint, a.model, cases, a.max_tokens)
    json.dump(rows, open(f"{a.out}/raw_{a.name}.json", "w"), ensure_ascii=False, indent=1)
    print(f"saved {a.out}/raw_{a.name}.json")


if __name__ == "__main__":
    main()
