import re, sys, json
bad=0
for line in sys.stdin:
    line=line.strip()
    if not line.startswith("{"): continue
    t=json.loads(line)["input"]
    stmts=re.findall(r"\b([A-Z][A-Za-z]+) says ([A-Z][A-Za-z]+) (tells the truth|lies)\b", t)
    toks=set(re.findall(r"\b[A-Z][a-z]+\b", t)) - {"Question","Does"}
    parsed=set(re.findall(r"\b([A-Z][A-Za-z]+)\b", " ".join(" ".join(s) for s in stmts)))
    n_says=t.count(" says ")
    if len(stmts)!=n_says or toks!=parsed: bad+=1; print("BAD", json.loads(line)["id"], n_says, len(stmts), sorted(toks^parsed))
print("anomalies", bad)
