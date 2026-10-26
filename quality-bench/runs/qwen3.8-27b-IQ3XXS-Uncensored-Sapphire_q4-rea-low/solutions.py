from typing import List


def reverse_delete(s, c):
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings, prefix):
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string):
    groups = []
    current = ""
    depth = 0
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


def strlen(string):
    return len(string)


def sorted_list_sum(lst):
    even = [s for s in lst if len(s) % 2 == 0]
    return sorted(even, key=lambda s: (len(s), s))


def sum_product(numbers):
    total = sum(numbers)
    product = 1
    for n in numbers:
        product *= n
    return (total, product)


def rescale_to_unit(numbers):
    lo = min(numbers)
    hi = max(numbers)
    return [(x - lo) / (hi - lo) for x in numbers]


def factorize(n):
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
    first = min(lst)
    for x in lst:
        if x != first:
            return x
    return None


def sum_to_n(n):
    return n * (n + 1) // 2


def mean_absolute_deviation(numbers):
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings, substring):
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    def strength(ext):
        cap = sum(1 for c in ext if c.isupper())
        sm = sum(1 for c in ext if c.islower())
        return cap - sm
    best = max(extensions, key=strength)
    return class_name + "." + best


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
            n //= 2
        else:
            n = 3 * n + 1
        seq.append(n)
    return sorted(set(x for x in seq if x % 2 == 1))


def get_closest_vowel(word):
    vowels = set("aeiouAEIOU")
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


def encode_cyclic(s):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def decode_cyclic(s):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    expr = str(operand[0])
    for i, op in enumerate(operator):
        expr += " " + op + " " + str(operand[i + 1])
    return eval(expr)


def fib4(n):
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
    if text == "":
        return None
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def below_zero(operations):
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
        if x < 0:
            sign_product *= -1
        elif x == 0:
            sign_product = 0
    magnitude_sum = sum(abs(x) for x in arr)
    return sign_product * magnitude_sum


def valid_date(date):
    import re
    if not date:
        return False
    if not re.match(r"^\d{2}-\d{1,2}-\d{4}$", date):
        return False
    mm, dd, yyyy = date.split("-")
    mm = int(mm)
    dd = int(dd)
    if mm < 1 or mm > 12:
        return False
    if dd < 1:
        return False
    if mm in (1, 3, 5, 7, 8, 10, 12):
        return dd <= 31
    if mm in (4, 6, 9, 11):
        return dd <= 30
    return dd <= 29


def fibfib(n):
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


def count_distinct_characters(string):
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    return n >= 8 and n % 2 == 0


def match_parens(lst):
    a, b = lst[0], lst[1]
    def is_good(s):
        depth = 0
        for ch in s:
            if ch == '(':
                depth += 1
            else:
                depth -= 1
            if depth < 0:
                return False
        return depth == 0
    return 'Yes' if (is_good(a + b) or is_good(b + a)) else 'No'


def parse_music(music_string):
    mapping = {'o': 4, 'o|': 2, '.|': 1}
    return [mapping[tok] for tok in music_string.split()]


def filter_integers(values):
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def digits(n):
    product = 1
    found_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            found_odd = True
    return product if found_odd else 0
