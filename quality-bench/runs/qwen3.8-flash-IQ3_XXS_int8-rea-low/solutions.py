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
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
            if depth == 0:
                result.append(current)
                current = ""
        elif ch.isspace():
            continue
        else:
            current += ch
    return result


def strlen(string: str) -> int:
    return len(string)


def sorted_list_sum(lst):
    words = [w for w in lst if len(w) % 2 == 0]
    words.sort(key=lambda w: (len(w), w))
    return words


def sum_product(numbers: List[int]):
    total = 0
    product = 1
    for n in numbers:
        total += n
        product *= n
    return (total, product)


def rescale_to_unit(numbers: List[float]) -> List[float]:
    lo = min(numbers)
    hi = max(numbers)
    span = hi - lo
    if span == 0:
        return [0.0 for _ in numbers]
    return [(x - lo) / span for x in numbers]


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
    unique = sorted(set(lst))
    if len(unique) < 2:
        return None
    return unique[1]


def sum_to_n(n: int):
    return n * (n + 1) // 2


def mean_absolute_deviation(numbers: List[float]) -> float:
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    best = None
    best_strength = None
    for ext in extensions:
        cap = sum(1 for ch in ext if ch.isupper())
        sm = sum(1 for ch in ext if ch.islower())
        strength = cap - sm
        if best_strength is None or strength > best_strength:
            best_strength = strength
            best = ext
    return class_name + "." + best


def sort_array(array):
    if not array:
        return []
    result = list(array)
    if (array[0] + array[-1]) % 2 == 0:
        result.sort(reverse=True)
    else:
        result.sort()
    return result


def get_odd_collatz(n):
    odd = set()
    m = n
    while m != 1:
        if m % 2 == 1:
            odd.add(m)
            m = 3 * m + 1
        else:
            m //= 2
    odd.add(1)
    return sorted(odd)


def get_closest_vowel(word):
    vowels = "aeiouAEIOU"
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


def encode_cyclic(s: str):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def decode_cyclic(s: str):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    expression = str(operand[0])
    for opr, num in zip(operator, operand[1:]):
        expression += opr + str(num)
    return eval(expression)


def fib4(n: int):
    a, b, c, d = 0, 0, 2, 0
    for _ in range(n):
        a, b, c, d = b, c, d, a + b + c + d
    return a


def string_to_md5(text):
    import hashlib
    if text == "":
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
    sign_product = 1
    magnitude_sum = 0
    for x in arr:
        if x > 0:
            sign_product *= 1
        elif x < 0:
            sign_product *= -1
        else:
            sign_product = 0
        magnitude_sum += abs(x)
    return magnitude_sum * sign_product


def valid_date(date):
    date = date.strip()
    if not date:
        return False
    parts = date.split("-")
    if len(parts) != 3:
        return False
    mm, dd, yyyy = parts
    if len(mm) != 2 or len(dd) != 2 or len(yyyy) != 4:
        return False
    digits = "0123456789"
    for part in (mm, dd, yyyy):
        for ch in part:
            if ch not in digits:
                return False
    month = int(mm)
    day = int(dd)
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12):
        return day <= 31
    if month in (4, 6, 9, 11):
        return day <= 30
    return day <= 29


def fibfib(n: int):
    if n < 2:
        return 0
    a, b, c = 0, 0, 1
    for _ in range(n - 2):
        a, b, c = b, c, a + b + c
    return c


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n % 2 == 0 and n >= 8


def match_parens(lst):
    def is_good(s):
        balance = 0
        for ch in s:
            if ch == "(":
                balance += 1
            else:
                balance -= 1
            if balance < 0:
                return False
        return balance == 0

    if is_good(lst[0] + lst[1]) or is_good(lst[1] + lst[0]):
        return "Yes"
    return "No"


def parse_music(music_string: str) -> List[int]:
    legend = {"o": 4, "o|": 2, ".|": 1}
    return [legend[note] for note in music_string.split() if note in legend]


def filter_integers(values):
    return [v for v in values if isinstance(v, int)]


def digits(n):
    product = 1
    found_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            found_odd = True
    return product if found_odd else 0
