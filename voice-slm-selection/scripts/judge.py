#!/usr/bin/env python3
"""LLM-as-judge: score each candidate's cleanup against the original + gold meaning."""
import argparse, json, re, time, urllib.request

JUDGE_SYS = (
    "Ты строгий судья качества пост-обработки расшифровок русской речи. "
    "Оцениваешь ОДИН вариант очистки исходного текста. Отвечай только JSON."
)

TPL = """Исходная расшифровка (с мусором и ошибками распознавания):
{raw}

Смысл, который был в виду (опора для оценки):
{gold}

Вариант очистки от модели «{name}»:
{out}

Оцени по шкале 0-10 каждое:
- meaning: смысл исходника полностью сохранён, ничего не потеряно и не переврано
- fix: исправлены ошибки распознавания, опечатки, расставлена пунктуация
- clean: убраны слова-паразиты, повторы, ли вода
- faithful: ничего не добавлено от себя, нет домысливания, нет пояснений и альтернатив
- concise: ответ короткий, ровно одна очищенная версия, без вступлений и разбора

Верни строго JSON вида {{"meaning":N,"fix":N,"clean":N,"faithful":N,"concise":N,"comment":"1-2 предложения"}}"""


def judge_call(url, model, prompt, max_tokens=700):
    body = json.dumps({"model": model,
                       "messages": [{"role": "system", "content": JUDGE_SYS},
                                    {"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.0,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    return (d["choices"][0]["message"]["content"] or "").strip()


def parse_json(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    return {k: float(d[k]) for k in ("meaning", "fix", "clean", "faithful", "concise")
            if isinstance(d.get(k), (int, float))} | {"comment": str(d.get("comment", ""))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-url", default="http://127.0.0.1:8080")
    ap.add_argument("--judge-model", default="qwen3.8-27b-IQ3XXS-Uncensored-ROCm-Sapphire")
    ap.add_argument("--results", default="results")
    ap.add_argument("--names", required=True, help="comma separated candidate names")
    ap.add_argument("--out", default="results/judged.json")
    a = ap.parse_args()

    scores = {}
    for name in a.names.split(","):
        rows = json.load(open(f"{a.results}/raw_{name}.json"))
        per = []
        for r in rows:
            prompt = TPL.format(raw=r["raw"], gold=r["gold_meaning"], name=name, out=r["out"])
            try:
                s = parse_json(judge_call(a.judge_url, a.judge_model, prompt))
            except Exception as e:
                s = None
                print(f"[judge] {name}/{r['id']} error {e}")
            if s is None:
                s = {"meaning": 0, "fix": 0, "clean": 0, "faithful": 0, "concise": 0, "comment": "judge failed"}
            s["id"] = r["id"]
            per.append(s)
            print(f"[judge] {name}/{r['id']} " + " ".join(f"{k}={s[k]}" for k in ("meaning", "fix", "clean", "faithful", "concise")))
            time.sleep(0.3)
        avg = {k: round(sum(p[k] for p in per) / len(per), 2) for k in ("meaning", "fix", "clean", "faithful", "concise")}
        avg["quality"] = round(sum(avg[k] for k in ("meaning", "fix", "clean", "faithful", "concise")) / 5, 2)
        avg["tps"] = round(sum(json.load(open(f"{a.results}/raw_{name}.json"))[i]["tps"] for i in range(len(per))) / len(per), 2)
        avg["cases"] = per
        scores[name] = avg
    json.dump(scores, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nsaved {a.out}")
    for n, s in sorted(scores.items(), key=lambda kv: -kv[1]["quality"]):
        print(f"{n:22s} quality={s['quality']:5.2f} tps={s['tps']:6.2f}  " +
              " ".join(f"{k}={s[k]}" for k in ("meaning", "fix", "clean", "faithful", "concise")))


if __name__ == "__main__":
    main()
