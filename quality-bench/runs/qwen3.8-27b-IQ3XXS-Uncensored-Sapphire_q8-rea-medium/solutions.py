from typing import List


def reverse_delete(s, c):
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    groups = []
    depth = 0
    current = ""
    for ch in paren_string:
        if ch == " ":
            continue
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
            if depth == 0:
                groups.append(current)
                current = ""
    return groups


def strlen(string: str) -> int:
    length = 0
    for _ in string:
        length += 1
    return length


def sorted_list_sum(lst):
    result = [s for s in lst if len(s) % 2 == 0]
    result.sort(key=lambda s: (len(s), s))
    return result


def sum_product(numbers: List[int]):
    product = 1
    for x in numbers:
        product *= x
    return (sum(numbers), product)


def rescale_to_unit(numbers: List[float]) -> List[float]:
    mn = min(numbers)
    mx = max(numbers)
    if mx == mn:
        return [0.0 for _ in numbers]
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
    distinct = sorted(set(lst))
    if len(distinct) < 2:
        return None
    return distinct[1]


def sum_to_n(n: int):
    return sum(range(1, n + 1))


def mean_absolute_deviation(numbers: List[float]) -> float:
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    def strength(ext):
        cap = sum(1 for ch in ext if ch.isupper())
        sm = sum(1 for ch in ext if ch.islower())
        return cap - sm
    best = max(extensions, key=lambda ext: strength(ext))
    return class_name + "." + best


def sort_array(array):
    result = array[:]
    if len(result) > 1 and (result[0] + result[-1]) % 2 == 0:
        result.sort(reverse=True)
    else:
        result.sort()
    return result


def get_odd_collatz(n):
    seq = []
    while n != 1:
        if n % 2 == 1:
            seq.append(n)
        if n % 2 == 0:
            n //= 2
        else:
            n = 3 * n + 1
    seq.append(1)
    return sorted(seq)


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
    parts = []
    for i, op in enumerate(operator):
        parts.append(str(operand[i]))
        parts.append(op)
    parts.append(str(operand[-1]))
    return eval(" ".join(parts))


def fib4(n: int):
    seq = [0, 0, 2, 0]
    for i in range(4, n + 1):
        seq.append(seq[i - 1] + seq[i - 2] + seq[i - 3] + seq[i - 4])
    return seq[n]


def string_to_md5(text):
    import hashlib
    if not text:
        return None
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
    sign = 1
    for x in arr:
        sign *= (1 if x > 0 else -1 if x < 0 else 0)
    return sign * sum(abs(x) for x in arr)


def valid_date(date):
    import re
    if not isinstance(date, str) or not date:
        return False
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", date)
    if not m:
        return False
    mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mm <= 12):
        return False
    if mm in (1, 3, 5, 7, 8, 10, 12):
        max_day = 31
    elif mm in (4, 6, 9, 11):
        max_day = 30
    else:
        max_day = 29
    return 1 <= dd <= max_day


def fibfib(n: int):
    seq = [0, 0, 1]
    for i in range(3, n + 1):
        seq.append(seq[i - 1] + seq[i - 2] + seq[i - 3])
    return seq[n]


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n >= 8 and n % 2 == 0


def match_parens(lst):
    def good(s):
        bal = 0
        for ch in s:
            bal += 1 if ch == "(" else -1
            if bal < 0:
                return False
        return bal == 0
    return "Yes" if good(lst[0] + lst[1]) or good(lst[1] + lst[0]) else "No"


def parse_music(music_string: str) -> List[int]:
    beats = {"o": 4, "o|": 2, ".|": 1}
    return [beats[t] for t in music_string.split(" ")]


def filter_integers(values):
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def digits(n):
    product = 1
    any_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            any_odd = True
    return product if any_odd else 0


def encode_cyclic(s: str):
    """
    returns encoded string by cycling groups of three characters.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # cycle elements in each group. Unless group has fewer elements than 3.
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)
