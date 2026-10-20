import os, csv, json, math, codecs, re
from collections import Counter

ROOT='/tasks/terminal_sandboxes_hard'
def rd(name):
    with open(os.path.join(ROOT,name)) as f:
        return [l.rstrip('\n').rstrip('\r') for l in f]
def out(task,val):
    p=os.path.join(ROOT,task,'out.txt')
    if os.path.exists(p): print('SKIP (already has out)', task); return
    with open(p,'w') as f: f.write(str(val).strip()+'\n')

# merge_sorted
a=[int(l.strip()) for l in rd('merge_sorted/a.txt')]
b=[int(l.strip()) for l in rd('merge_sorted/b.txt')]
out('merge_sorted', sorted(a+b)[49])

env=rd('env_count/.env'); out('env_count', sum(1 for l in env if l.startswith('export ')))
tot=sum(1 for l in rd('props_count/app.properties') if l.split('=')[0].strip().startswith('db.connection'))
out('props_count', tot)
dl=[l.strip().split()[0] for l in rd('dockerfile_layers/Dockerfile') if l.strip()]
out('dockerfile_layers', sum(1 for t in dl if t=='RUN'))

# dns_zone: task says type is 4th field of '<name> <ttl> IN <type> <data>' -> index 3; verify structure first
z=rd('dns_zone/zone.txt')
bad=[l for l in z if len(l.split())!=5]
assert not bad, bad[:2]
zc=Counter(l.split()[3] for l in z)
out('dns_zone', zc.most_common(1)[0][0])

ips={t[0] for t in (l.split() for l in rd('fw_blocked/fw.log')) if len(t)>=2 and t[1]=='BLOCK'}
out('fw_blocked', len(ips))

# fixed_width: derive columns from data (name 8, age 4, salary 6); cross-check with whitespace split
rows=rd('fixed_width/data.txt')
totA=sum(int(l[12:18]) for l in rows if int(l[8:12])>40)
for l in rows:
    t=l.split()
    assert len(t)==3 and int(l[8:12])==int(t[1]) and int(l[12:18])==int(t[-1]), repr(l)
totB=sum(int(t[-1]) for t in (l.split() for l in rows) if int(t[1])>40)
assert totA==totB, (totA,totB)
out('fixed_width', totA)

# ini_sum [sec4]
tot=0; sec=None
for l in rd('ini_sum/config.ini'):
    s=l.strip()
    if not s or s[0] in '#;': continue
    if s.startswith('['): sec=s.strip('[]'); continue
    k,_,v=s.partition('=')
    if sec=='sec4' and v.strip().lstrip('-').isdigit(): tot+=int(v)
out('ini_sum', tot)

# join_vip_revenue
with open(os.path.join(ROOT,'join_vip_revenue/customers.csv')) as f: rows=list(csv.DictReader(f))
vip={r['id'] for r in rows if r['tier']=='VIP'}
tot=0.0; n=0
with open(os.path.join(ROOT,'join_vip_revenue/orders.csv')) as f:
    for r in csv.DictReader(f):
        if r['customer_id'] in vip: tot+=float(r['amount']); n+=1
print('vip orders',n); out('join_vip_revenue', int(round(tot)))

tot=0.0; n=0
for l in rd('jsonl_sum/data.jsonl'):
    o=json.loads(l)
    if o['val']>50: tot+=o['val']; n+=1
print('jsonl rows>50',n); out('jsonl_sum', int(round(tot)))

tot=0.0; n=0
with open(os.path.join(ROOT,'quoted_csv/items.csv')) as f:
    for r in csv.DictReader(f):
        if ',' in r['description']: tot+=float(r['price']); n+=1
print('quoted rows w/ comma',n); out('quoted_csv', int(round(tot)))

cur=mx=0; neg_clamp=0
for l in rd('max_concurrency/events.log'):
    ev=l.split()[1]
    cur += 1 if ev=='login' else -1
    if cur<0: cur=0; neg_clamp+=1
    mx=max(mx,cur)
print('clamps',neg_clamp); out('max_concurrency', mx)

parent=list(range(50))
def find(x):
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
for l in rd('graph_components/edges.txt'):
    a,bd=map(int,l.split()); ra,rb=find(a),find(bd)
    if ra!=rb: parent[ra]=rb
out('graph_components', len({find(i) for i in range(50)}))

hx=open(os.path.join(ROOT,'hex_decode/data.hex')).read().strip()
dec=bytes.fromhex(hx).decode(); out('hex_decode', dec); print('hex ->',repr(dec))

found=None
for l in rd('rot13_find/encoded.txt'):
    d=codecs.decode(l.strip(),'rot_13')
    if d.startswith('key-'): found=d; break
assert found, 'no key- line'
out('rot13_find', found); print('rot13 ->',found)

toks=open(os.path.join(ROOT,'rpn_eval/expr.txt')).read().split()
st=[]
for t in toks:
    if re.fullmatch(r'[+\-*/%]',t):
        b,a=st.pop(),st.pop()
        r = {'+':a+b, '-':a-b, '*':a*b, '%':a%b}
        st.append(r[t] if t in r else a//b)
    else: st.append(int(t))
out('rpn_eval', int(st[0]))

d=mx2=0
for ch in rd('paren_depth/code.txt')[0]:
    if ch=='(': d+=1; mx2=max(mx2,d)
    elif ch==')': d-=1
assert d==0, 'unbalanced'
out('paren_depth', mx2)

R={'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
def roman(s):
    v=0; p=None
    for ch in s:
        x=R[ch]
        if p is not None and x>p: v-=p
        v+=x; p=x
    return v
out('roman_sum', sum(roman(l.strip()) for l in rd('roman_sum/romans.txt')))

tot=sum(int(x.strip()) for x in rd('multi_bug_script/data.txt') if int(x.strip())%2!=0)
out('multi_bug_script', tot)
print('pass2 done')
