from typing import List


def reverse_delete(s, c):
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    result = []
    current = ""
    depth = 0
    for ch in paren_string:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
            if depth == 0:
                result.append(current)
                current = ""
    return result


def strlen(string: str) -> int:
    return len(string)


def sorted_list_sum(lst):
    lst = [w for w in lst if len(w) % 2 == 0]
    lst.sort(key=lambda w: (len(w), w))
    return lst


def sum_product(numbers):
    s = 0
    p = 1
    for n in numbers:
        s += n
        p *= n
    return (s, p)


def rescale_to_unit(numbers: List[float]) -> List[float]:
    mn = min(numbers)
    mx = max(numbers)
    return [(x - mn) / (mx - mn) for x in numbers]


def factorize(n: int) -> List[int]:
    factors = []
    d = 2
    while n > 1:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    return factors


def next_smallest(lst):
    uniq = sorted(set(lst))
    if len(uniq) < 2:
        return None
    return uniq[1]


def sum_to_n(n: int):
    return n * (n + 1) // 2


def mean_absolute_deviation(numbers: List[float]) -> float:
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    def strength(ext):
        cap = sum(1 for c in ext if c.isupper())
        sm = sum(1 for c in ext if c.islower())
        return cap - sm
    best = max(extensions, key=strength)
    return class_name + '.' + best


def sort_array(array):
    if not array:
        return []
    if (array[0] + array[-1]) % 2 == 1:
        return sorted(array)
    return sorted(array, reverse=True)


def get_odd_collatz(n):
    res = []
    while n != 1:
        if n % 2 == 1:
            res.append(n)
            n = 3 * n + 1
        else:
            n //= 2
    res.append(1)
    return sorted(res)


def get_closest_vowel(word):
    vowels = "aeiouAEIOU"
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


def decode_cyclic(s: str):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    ops = {'+': '+', '-': '-', '*': '*', '//': '//', '**': '**'}
    expr = str(operand[0])
    for op, val in zip(operator, operand[1:]):
        expr += ' ' + ops[op] + ' ' + str(val)
    return eval(expr)


def fib4(n: int):
    a, b, c, d = 0, 0, 2, 0
    if n == 0:
        return 0
    if n == 1:
        return 0
    if n == 2:
        return 2
    if n == 3:
        return 0
    for _ in range(4, n + 1):
        a, b, c, d = b, c, d, a + b + c + d
    return d


def string_to_md5(text):
    import hashlib
    if not text:
        return None
    return hashlib.md5(text.encode()).hexdigest()


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
    prod = 1
    total = 0
    for x in arr:
        if x == 0:
            prod = 0
        elif x > 0:
            prod *= 1
        else:
            prod *= -1
        total += abs(x)
    return prod * total


def valid_date(date):
    if not date:
        return False
    parts = date.split('-')
    if len(parts) != 3:
        return False
    if not all(p.isdigit() for p in parts):
        return False
    mm, dd, yy = (int(p) for p in parts)
    if mm < 1 or mm > 12:
        return False
    if mm in (1, 3, 5, 7, 8, 10, 12):
        mx = 31
    elif mm in (4, 6, 9, 11):
        mx = 30
    else:
        mx = 29
    if dd < 1 or dd > mx:
        return False
    return True


def fibfib(n: int):
    a, b, c = 0, 0, 1
    if n == 0:
        return 0
    if n == 1:
        return 0
    if n == 2:
        return 1
    for _ in range(3, n + 1):
        a, b, c = b, c, a + b + c
    return c


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n % 2 == 0 and n >= 8


def match_parens(lst):
    def good(s):
        d = 0
        for ch in s:
            if ch == '(':
                d += 1
            else:
                d -= 1
            if d < 0:
                return False
        return d == 0
    a, b = lst[0], lst[1]
    if good(a + b) or good(b + a):
        return 'Yes'
    return 'No'


def parse_music(music_string: str) -> List[int]:
    legend = {'o': 4, 'o|': 2, '.|': 1}
    return [legend[tok] for tok in music_string.split(' ') if tok]


def filter_integers(values):
    return [v for v in values if isinstance(v, int)]


def digits(n):
    prod = 1
    found = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            prod *= d
            found = True
    return prod if found else 0


def encode_cyclic(s: str):
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # cycle elements in each group. Unless group has fewer elements than 3.
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)
