import re, sys, json, collections

def solve(text):
    m = re.search(r"\b([A-Z][A-Za-z]+) (tells the truth|lies)\b", text)
    if not m: return None
    val = {m.group(1): (m.group(2) == "tells the truth")}
    stmts = re.findall(r"\b([A-Z][A-Za-z]+) says ([A-Z][A-Za-z]+) (tells the truth|lies)\b", text)
    q = re.search(r"Does ([A-Z][A-Za-z]+) tell the truth\?", text)
    if not q: return None
    adj = collections.defaultdict(list)   # edge (y, parity) : val(y) = val(x) XOR parity
    for x, y, kind in stmts:
        claim = (kind == "tells the truth")
        parity = 0 if claim else 1        # claim true -> same, claim false -> different
        adj[x].append((y, parity)); adj[y].append((x, parity))
    dq = collections.deque(val.keys())
    while dq:
        x = dq.popleft()
        for y, p in adj[x]:
            nv = (val[x] != bool(p))
            if y in val:
                if val[y] != nv: return "CONTRADICTION"
            else:
                val[y] = nv; dq.append(y)
    tgt = q.group(1)
    if tgt not in val: return "UNKNOWN"
    return "Yes" if val[tgt] else "No"

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    d = json.loads(line); v=solve(d["input"]);
    print(d["id"], v)
