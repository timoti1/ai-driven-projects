from typing import List


def reverse_delete(s, c):
    """Task"""
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    result = []
    current = []
    depth = 0
    for ch in paren_string:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
            if depth == 0:
                result.append(''.join(current))
                current = []
    return result


def strlen(string: str) -> int:
    return len(string)


def sorted_list_sum(lst):
    lst = [w for w in lst if len(w) % 2 == 0]
    lst.sort(key=lambda w: (len(w), w))
    return lst


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
    return class_name + '.' + best


def sort_array(array):
    if not array:
        return []
    if (array[0] + array[-1]) % 2 == 0:
        return sorted(array, reverse=True)
    return sorted(array)


def get_odd_collatz(n):
    odds = []
    while n != 1:
        if n % 2 == 1:
            odds.append(n)
        n = n // 2 if n % 2 == 0 else 3 * n + 1
    odds.append(1)
    return sorted(odds)


def get_closest_vowel(word):
    vowels = "AEIOUaeiou"
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


def encode_cyclic(s: str):
    """
    returns encoded string by cycling groups of three characters.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # cycle elements in each group. Unless group has fewer elements than 3.
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def decode_cyclic(s: str):
    """
    takes as input string encoded with encode_cyclic function. Returns decoded string.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # move elements back in each group. Unless group has fewer elements than 3.
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    expression = str(operand[0])
    for op, num in zip(operator, operand[1:]):
        expression += op + str(num)
    return eval(expression)


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
    for _ in range(4, n + 1):
        a, b, c, d = b, c, d, a + b + c + d
    return d


def string_to_md5(text):
    import hashlib
    if not text:
        return None
    return hashlib.md5(text.encode('utf-8')).hexdigest()


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
    product = 1
    total = 0
    for x in arr:
        if x > 0:
            product *= 1
        elif x < 0:
            product *= -1
        else:
            product = 0
        total += abs(x)
    return product * total


def valid_date(date):
    if not date:
        return False
    parts = date.split('-')
    if len(parts) != 3:
        return False
    try:
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return False
    for part in parts:
        if not part.isdigit():
            return False
    if month < 1 or month > 12:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 1 <= day <= 31
    if month in (4, 6, 9, 11):
        return 1 <= day <= 30
    return 1 <= day <= 29


def fibfib(n: int):
    if n == 0:
        return 0
    if n == 1:
        return 0
    if n == 2:
        return 1
    a, b, c = 0, 0, 1
    for _ in range(3, n + 1):
        a, b, c = b, c, a + b + c
    return c


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n % 2 == 0 and n >= 8


def match_parens(lst):
    def good(s):
        depth = 0
        for ch in s:
            if ch == '(':
                depth += 1
            else:
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    a, b = lst[0], lst[1]
    if good(a + b) or good(b + a):
        return 'Yes'
    return 'No'


def parse_music(music_string: str) -> List[int]:
    legend = {'o': 4, 'o|': 2, '.|': 1}
    return [legend[note] for note in music_string.split() if note]


def filter_integers(values: List[int]) -> List[int]:
    return [x for x in values if isinstance(x, int) and not isinstance(x, bool)]


def digits(n):
    product = 1
    found = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            found = True
    return product if found else 0
