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
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
            if depth == 0:
                groups.append(current)
                current = ""
        elif ch != ' ':
            current += ch
    return groups


def strlen(string: str) -> int:
    return len(string)


def sorted_list_sum(lst):
    even = [s for s in lst if len(s) % 2 == 0]
    return sorted(even, key=lambda x: (len(x), x))


def sum_product(numbers: List[int]):
    s = sum(numbers)
    p = 1
    for n in numbers:
        p *= n
    return (s, p)


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
    def strength(ext):
        cap = sum(1 for c in ext if c.isupper())
        sm = sum(1 for c in ext if c.islower())
        return cap - sm
    best = 0
    for i in range(1, len(extensions)):
        if strength(extensions[i]) > strength(extensions[best]):
            best = i
    return f"{class_name}.{extensions[best]}"


def sort_array(array):
    if len(array) <= 1:
        return array[:]
    if (array[0] + array[-1]) % 2 == 1:
        return sorted(array)
    else:
        return sorted(array, reverse=True)


def get_odd_collatz(n):
    seq = [n]
    while n != 1:
        if n % 2 == 0:
            n = n // 2
        else:
            n = 3 * n + 1
        seq.append(n)
    return sorted(set(x for x in seq if x % 2 == 1))


def get_closest_vowel(word):
    vowels = set('aeiouAEIOU')
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i-1] not in vowels and word[i+1] not in vowels:
            return word[i]
    return ""


def decode_cyclic(s: str):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    result = operand[0]
    for i, op in enumerate(operator):
        if op == '+':
            result += operand[i + 1]
        elif op == '-':
            result -= operand[i + 1]
        elif op == '*':
            result *= operand[i + 1]
        elif op == '//':
            result //= operand[i + 1]
        elif op == '**':
            result **= operand[i + 1]
    return result


def fib4(n: int):
    if n == 0:
        return 0
    if n == 1:
        return 0
    if n == 2:
        return 2
    if n == 3:
        return 0
    a, b, c, d = 0, 0, 2, 0
    for i in range(4, n + 1):
        a, b, c, d = b, c, d, a + b + c + d
    return d


def string_to_md5(text):
    if not text:
        return None
    import hashlib
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
    for x in arr:
        if x > 0:
            sign_product *= 1
        elif x < 0:
            sign_product *= -1
        else:
            sign_product *= 0
    magnitude_sum = sum(abs(x) for x in arr)
    return magnitude_sum * sign_product


def valid_date(date):
    import re
    if not date:
        return False
    if not re.match(r'^\d{2}-\d{1,2}-\d{4}$', date):
        return False
    parts = date.split('-')
    month = int(parts[0])
    day = int(parts[1])
    year = int(parts[2])
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12):
        return day <= 31
    elif month in (4, 6, 9, 11):
        return day <= 30
    elif month == 2:
        return day <= 29
    return False


def fibfib(n: int):
    if n == 0:
        return 0
    if n == 1:
        return 0
    if n == 2:
        return 1
    a, b, c = 0, 0, 1
    for i in range(3, n + 1):
        a, b, c = b, c, a + b + c
    return c


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n >= 8 and n % 2 == 0


def match_parens(lst):
    for order in [lst[0] + lst[1], lst[1] + lst[0]]:
        depth = 0
        valid = True
        for ch in order:
            if ch == '(':
                depth += 1
            else:
                depth -= 1
            if depth < 0:
                valid = False
                break
        if valid and depth == 0:
            return 'Yes'
    return 'No'


def parse_music(music_string: str) -> List[int]:
    notes = music_string.split()
    result = []
    for note in notes:
        if note == 'o':
            result.append(4)
        elif note == 'o|':
            result.append(2)
        elif note == '.|':
            result.append(1)
    return result


def filter_integers(values):
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def digits(n):
    product = 1
    all_even = True
    for d in str(n):
        digit = int(d)
        if digit % 2 != 0:
            product *= digit
            all_even = False
    if all_even:
        return 0
    return product


def encode_cyclic(s: str):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)
