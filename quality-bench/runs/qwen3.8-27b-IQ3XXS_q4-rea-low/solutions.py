from typing import List


def reverse_delete(s, c):
    for ch in set(c):
        s = s.replace(ch, "")
    return (s, s == s[::-1])

def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    result = []
    for x in strings:
        if x.startswith(prefix):
            result.append(x)
    return result

def separate_paren_groups(paren_string: str) -> List[str]:
    groups = []
    current = ""
    depth = 0
    for ch in paren_string.replace(" ", ""):
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
            if depth == 0 and current != "":
                groups.append(current)
                current = ""
    return groups

def strlen(string: str) -> int:
    count = 0
    for _ in string:
        count += 1
    return count

def sorted_list_sum(lst):
    evens = [x for x in lst if len(x) % 2 == 0]
    return sorted(evens, key=lambda s: (len(s), s))

def sum_product(numbers: List[int]):
    total = 0
    product = 1
    for n in numbers:
        total += n
        product *= n
    return (total, product)

def rescale_to_unit(numbers: List[float]) -> List[float]:
    mn = min(numbers)
    mx = max(numbers)
    if mx == mn:
        return [0.0] * len(numbers)
    return [(x - mn) / (mx - mn) for x in numbers]

def factorize(n: int) -> List[int]:
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors

def next_smallest(lst):
    if len(lst) < 2:
        return None
    m = min(lst)
    for x in lst:
        if x > m:
            return x
    return None

def sum_to_n(n: int):
    total = 0
    i = 1
    while i <= n:
        total += i
        i += 1
    return total

def mean_absolute_deviation(numbers: List[float]) -> float:
    n = len(numbers)
    m = sum(numbers) / n
    return sum(abs(x - m) for x in numbers) / n

def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    result = []
    for x in strings:
        if substring in x:
            result.append(x)
    return result

def Strongest_Extension(class_name, extensions):
    def strength(e):
        cap = sum(1 for ch in e if ch.isupper())
        sm = sum(1 for ch in e if ch.islower())
        return cap - sm
    best = max(extensions, key=strength)
    return class_name + "." + best

def sort_array(array):
    a = list(array)
    if len(a) <= 1:
        return a
    s = a[0] + a[-1]
    if s % 2 == 1:
        return sorted(a)
    else:
        return sorted(a, reverse=True)

def get_odd_collatz(n):
    odds = set()
    cur = n
    while True:
        if cur % 2 == 1:
            odds.add(cur)
        if cur == 1:
            break
        if cur % 2 == 0:
            cur //= 2
        else:
            cur = 3 * cur + 1
    return sorted(odds)

def get_closest_vowel(word):
    v = set("aeiouAEIOU")
    for i in range(len(word) - 2, 0, -1):
        if word[i] in v and word[i-1] not in v and word[i+1] not in v:
            return word[i]
    return ""

def decode_cyclic(s: str):
    # helper from the task prompt, kept verbatim so this file is self-contained
    def encode_cyclic(x: str):
        groups = [x[(3 * i):min((3 * i + 3), len(x))] for i in range((len(x) + 2) // 3)]
        groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
        return "".join(groups)

    # split string to groups, each of length 3; inverse the left rotation per full group.
    out = []
    for g in [s[(3 * i):min(3 * (i + 1), len(s))] for i in range((len(s) + 2) // 3)]:
        if len(g) == 3:
            out.append(g[2] + g[:2])
        else:
            out.append(g)
    return "".join(out)

def do_algebra(operator, operand):
    expr = str(operand[0])
    for op, x in zip(operator, operand[1:]):
        expr += " " + op + " " + str(x)
    return int(eval(expr))

def fib4(n: int):
    if n <= 3:
        return [0, 0, 2, 0][n]
    seq = [0, 0, 2, 0]
    for i in range(4, n + 1):
        seq.append(seq[i-1] + seq[i-2] + seq[i-3] + seq[i-4])
    return seq[n]

def string_to_md5(text):
    if text == "":
        return None
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def below_zero(operations: List[int]) -> bool:
    balance = 0
    for op in operations:
        balance += op
        if balance < 0:
            return True
    return False

def prod_signs(arr):
    if not arr:
        return None
    sign_product = 1
    magnitude_sum = 0
    for x in arr:
        if x == 0:
            sign_product = 0
        elif x < 0:
            sign_product *= -1
        else:
            sign_product *= 1
        magnitude_sum += abs(x)
    return sign_product * magnitude_sum

def valid_date(date):
    import re
    if not date or "-" not in date:
        return False
    parts = date.split("-")
    if len(parts) != 3:
        return False
    try:
        mm, dd, yyyy = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return False
    if not (1 <= mm <= 12):
        return False
    if not (1 <= dd):
        return False
    if mm in (4, 6, 9, 11):
        max_day = 30
    elif mm == 2:
        max_day = 29
    else:
        max_day = 31
    return dd <= max_day

def fibfib(n: int):
    if n < 3:
        return [0, 0, 1][n]
    seq = [0, 0, 1]
    for i in range(3, n + 1):
        seq.append(seq[i-1] + seq[i-2] + seq[i-3])
    return seq[n]

def count_distinct_characters(string: str) -> int:
    seen = set()
    for ch in string.lower():
        seen.add(ch)
    return len(seen)

def is_equal_to_sum_even(n):
    return n >= 8 and n % 2 == 0

def match_parens(lst):
    a, b = lst[0], lst[1]
    def balanced(s):
        depth = 0
        for ch in s:
            if ch == "(":
                depth += 1
            else:
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0
    return "Yes" if balanced(a + b) or balanced(b + a) else "No"

def parse_music(music_string: str) -> List[int]:
    beats = {"o": 4, "o|": 2, ".|": 1}
    result = []
    for note in music_string.split():
        result.append(beats[note])
    return result

def filter_integers(values):
    result = []
    for v in values:
        if isinstance(v, int) and not isinstance(v, bool):
            result.append(v)
    return result

def digits(n):
    product = 1
    has_odd = False
    for ch in str(abs(n)):
        d = ord(ch) - ord("0")
        if d % 2 == 1:
            product *= d
            has_odd = True
    return product if has_odd else 0


