import os, csv, json, base64, math, codecs, heapq, re
from collections import Counter
from functools import reduce
from urllib.parse import urlparse

ROOT = '/tasks/terminal_sandboxes_hard'

def rd(name):  # read lines (no trailing newlines) of file in task dir
    with open(os.path.join(ROOT, name)) as f:
        return [l.rstrip('\n').rstrip('\r') for l in f if True]

def nums_of(task):
    return [int(l.strip()) for l in rd(f'{task}/nums.txt')]

def out(task, val):
    with open(os.path.join(ROOT, task, 'out.txt'), 'w') as f:
        f.write(str(val).strip() + '\n')

# anagram_groups
c = Counter(''.join(sorted(w.strip())) for w in rd('anagram_groups/words.txt'))
out('anagram_groups', sum(1 for v in c.values() if v >= 2))

# anti_join_products
prods, orders = set(rd('anti_join_products/products.csv')), set(rd('anti_join_products/orders.csv'))
out('anti_join_products', len(prods - orders))

# base64_decode_count
txt = base64.b64decode(open(os.path.join(ROOT,'base64_decode_count/data.b64')).read().strip()).decode()
out('base64_decode_count', len(set(txt.split())))

# bfs_shortest (Dijkstra)
g = {}
for l in rd('bfs_shortest/edges.txt'):
    a,b,w = map(int, l.split())
    g.setdefault(a,[]).append((w,b)); g.setdefault(b,[]).append((w,a))
dist = {0:0}; pq=[(0,0)]
while pq:
    d,u = heapq.heappop(pq)
    if d > dist.get(u,1e18): continue
    for w,v in g.get(u,[]):
        nd = d+w
        if nd < dist.get(v,1e18):
            dist[v]=nd; heapq.heappush(pq,(nd,v))
out('bfs_shortest', dist.get(29,-1))

# bit_count / collatz / every_kth / max_subarray / sliding_window / two_sum / xor_list
ns = nums_of('bit_count'); out('bit_count', sum(bin(n).count('1') for n in ns))
n = int(open(os.path.join(ROOT,'collatz/n.txt')).read().strip()); s=0
while n!=1:
    n = n//2 if n%2==0 else 3*n+1; s+=1
out('collatz', s)
ns = nums_of('every_kth'); out('every_kth', sum(ns[i] for i in range(0,len(ns),7)))
# max_subarray (Kadane, allow empty? no — contiguous subarray non-empty)
best=cur=None
for x in nums_of('max_subarray'):
    cur = x if cur is None else max(x, cur+x); best = cur if best is None else max(best,cur)
out('max_subarray', best)
ns = nums_of('sliding_window'); out('sliding_window', max(sum(ns[i:i+10]) for i in range(len(ns)-9)))
# two_sum pairs summing to 30 (i<j multiset counting)
cnt=Counter(); tot=0
for x in nums_of('two_sum'):
    tot += cnt[30-x]; cnt[x]+=1
out('two_sum', tot)
out('xor_list', reduce(lambda a,b:a^b, nums_of('xor_list')))

# duplicate_number / missing_number / gcd_list / lcm_list
ns = Counter(nums_of('duplicate_number'))
out('duplicate_number', [k for k,v in ns.items() if v==2][0])
ns = set(nums_of('missing_number')); N=max(ns)
miss=[x for x in range(1,N+1) if x not in ns]
assert len(miss)==1, miss
out('missing_number', miss[0])
out('gcd_list', reduce(math.gcd, nums_of('gcd_list')))
out('lcm_list', reduce(lambda a,b: math.lcm(a,b), nums_of('lcm_list')))

# pos_subarray (n=50 brute force)
ns = nums_of('pos_subarray'); tot=0
for i in range(len(ns)):
    s=0
    for j in range(i,len(ns)):
        s+=ns[j]
        if s>0: tot+=1
out('pos_subarray', tot)

# primes_count (sieve, inclusive)
lo,hi = [int(x.strip()) for x in rd('primes_count/range.txt')]
if hi < 2: out('primes_count',0); raise SystemExit
is_p = bytearray([1])*(hi+1); is_p[0]=is_p[1]=0
for p in range(2,int(hi**0.5)+1):
    if is_p[p]:
        for q in range(p*p, hi+1, p): is_p[q]=0
out('primes_count', sum(is_p[lo:hi+1]))

# date_latest / longest_line / word_tiebreak / url_domain / version_sort / natural_sort
ds = rd('date_latest/events.txt'); out('date_latest', max(ds))
ls_ = [len(l) for l in open(os.path.join(ROOT,'longest_line/lines.txt')).read().split('\n') if l!='']
out('longest_line', max(ls_))
wc = Counter(w.strip() for w in rd('word_tiebreak/corpus.txt')[0].split())
m=max(wc.values()); out('word_tiebreak', min(w for w,c in wc.items() if c==m))
uc=Counter(urlparse(u).hostname for u in rd('url_domain/urls.txt'))
out('url_domain', uc.most_common(1)[0][0])
vers=[l.strip() for l in rd('version_sort/versions.txt')]
best=max((tuple(map(int,v.split('.'))), v) for v in vers); out('version_sort', best[1])
fn=os.path.join(ROOT,'natural_sort/files')
names=sorted(os.listdir(fn), key=lambda f:int(re.search(r'file(\d+)\.txt',f).group(1)))
out('natural_sort', names[4])

# file_intersection / full_outer_keys / sym_diff / merge_sorted
A=set(rd('file_intersection/a.txt')); B=set(rd('file_intersection/b.txt'))
out('file_intersection', len(A&B))
A=set(rd('full_outer_keys/a.txt')); B=set(rd('full_outer_keys/b.txt'))
out('full_outer_keys', len(A|B))
A=set(rd('sym_diff/a.txt')); B=set(rd('sym_diff/b.txt'))
out('sym_diff', len(A^B))
merged=sorted(nums_of2 for nums_of2 in [nums_of('merge_sorted')])  # placeholder replaced below

# merge_sorted properly (two files)
a=[int(l.strip()) for l in rd('merge_sorted/a.txt')]
b=[int(l.strip()) for l in rd('merge_sorted/b.txt')]
out('merge_sorted', sorted(a+b)[49])

# env_count / props_count / dockerfile_layers / dns_zone / fw_blocked
env=rd('env_count/.env'); out('env_count', sum(1 for l in env if l.startswith('export ')))
tot=0
for l in rd('props_count/app.properties'):
    k=l.split('=')[0].strip()
    if k.startswith('db.connection'): tot+=1
out('props_count', tot)
dl=[l.strip().split()[0] for l in rd('dockerfile_layers/Dockerfile') if l.strip()]
out('dockerfile_layers', sum(1 for t in dl if t=='RUN'))
zc=Counter(l.split()[-3+1-2+3][0:0] or '' for _ in [0])  # placeholder, replaced below

# dns_zone properly: type is the field right before data; task says 4th field of '<name> <ttl> IN <type> <data>'
zc=Counter(l.split()[3] for l in rd('dns_zone/zone.txt'))
out('dns_zone', zc.most_common(1)[0][0])

# fw_blocked: distinct IPs with action BLOCK (fields per task: ip, action, 'port', port)
ips=set()
for l in rd('fw_blocked/fw.log'):
    t=l.split()
    if len(t)>=2 and t[1]=='BLOCK': ips.add(t[0])
out('fw_blocked', len(ips))

# fixed_width: name 8, age 4, salary 6 (positions from data)
tot=0
for l in rd('fixed_width/data.txt'):
    if not l.strip(): continue
    age=int(l[8:12]); sal=int(l[12:18])
    if age>40: tot+=sal
out('fixed_width', tot)

# ini_sum: sum int values under [sec4]
tot=0; sec=None
for l in rd('ini_sum/config.ini'):
    s=l.strip()
    if not s or s.startswith('#') or s.startswith(';'): continue
    if s[0]=='[' and s[-1]==']': sec=s[1:-1]; continue
    k,_,v=s.partition('=')
    if sec=='sec4' and v.strip().lstrip('-').isdigit(): tot+=int(v)
out('ini_sum', tot)

# join_vip_revenue (csv module; headers id,tier / id,customer_id,amount)
with open(os.path.join(ROOT,'join_vip_revenue/customers.csv')) as f:
    rows=list(csv.DictReader(f))
vip={r['id'] for r in rows if r['tier']=='VIP'}
tot=0.0; n=0
with open(os.path.join(ROOT,'join_vip_revenue/orders.csv')) as f:
    for r in csv.DictReader(f):
        if r['customer_id'] in vip: tot+=float(r['amount']); n+=1
out('join_vip_revenue', int(round(tot)))

# jsonl_sum
tot=0.0; n=0
for l in rd('jsonl_sum/data.jsonl'):
    o=json.loads(l)
    if o['val']>50: tot+=o['val']; n+=1
out('jsonl_sum', int(round(tot)))

# quoted_csv (csv module handles commas inside quotes)
tot=0.0; n=0
with open(os.path.join(ROOT,'quoted_csv/items.csv')) as f:
    for r in csv.DictReader(f):
        if ',' in r['description']: tot+=float(r['price']); n+=1
out('quoted_csv', int(round(tot)))

# max_concurrency (clamp at 0)
cur=mx=0
for l in rd('max_concurrency/events.log'):
    ev=l.split()[1]
    cur += 1 if ev=='login' else -1
    if cur<0: cur=0
    mx=max(mx,cur)
out('max_concurrency', mx)

# graph_components (nodes 0..49 union-find)
parent=list(range(50))
def find(x):
    while parent[x]!=x:
        parent[x]=parent[parent[x]]; x=parent[x]
    return x
for l in rd('graph_components/edges.txt'):
    a,b=map(int,l.split())
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb
out('graph_components', len({find(i) for i in range(50)}))

# hex_decode / rot13_find / rpn_eval / paren_depth / roman_sum
hx=open(os.path.join(ROOT,'hex_decode/data.hex')).read().strip()
out('hex_decode', bytes.fromhex(hx).decode())
for l in rd('rot13_find/encoded.txt'):
    d=codecs.decode(l, 'rot_13')
    if d.startswith('key-'): out('rot13_find', d); break
toks=open(os.path.join(ROOT,'rpn_eval/expr.txt')).read().split()
st=[]
for t in toks:
    if t in '+-*/%':
        b,a=st.pop(),st.pop()
        st.append({'+':a+b,'-':a-b,'*':a*b,'%':a%b}[t] if t!='/' else a//b)
    else: st.append(int(t))
out('rpn_eval', int(st[0]))
d=mx2=0
for ch in rd('paren_depth/code.txt')[0]:
    if ch=='(': d+=1; mx2=max(mx2,d)
    elif ch==')': d-=1
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

# multi_bug_script: compute correct answer independently (sum of odd numbers)
tot=sum(int(x.strip()) for x in rd('multi_bug_script/data.txt') if int(x.strip())%2!=0)
out('multi_bug_script', tot)

print("done")
