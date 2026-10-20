from typing import List


def reverse_delete(s, c):
    for ch in set(c):
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    return [string for string in strings if string.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    result = []
    current = ""
    depth = 0
    for ch in paren_string.replace(" ", ""):
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
            if depth == 0:
                result.append(current)
                current = ""
    return result


def strlen(string: str) -> int:
    count = 0
    for _ in string:
        count += 1
    return count


def sorted_list_sum(lst):
    even_len_words = [s for s in lst if len(s) % 2 == 0]
    return sorted(even_len_words, key=lambda x: (len(x), x))


def sum_product(numbers: List[int]):
    total = 0
    prod = 1
    for n in numbers:
        total += n
        prod *= n
    return (total, prod)


def rescale_to_unit(numbers: List[float]) -> List[float]:
    mn = min(numbers)
    mx = max(numbers)
    if mx == mn:
        return [0.0 for _ in numbers]
    scale = 1.0 / (mx - mn)
    return [(x - mn) * scale for x in numbers]


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
    total = 0
    for i in range(1, n + 1):
        total += i
    return total


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

    strongest = max(range(len(extensions)), key=lambda i: strength(extensions[i]))
    return class_name + "." + extensions[strongest]


def sort_array(array):
    arr = list(array)
    if len(arr) <= 1:
        return arr
    if (arr[0] + arr[-1]) % 2 == 1:
        return sorted(arr)
    else:
        return sorted(arr, reverse=True)


def get_odd_collatz(n):
    odd_set = set()
    while n != 1:
        if n % 2 == 1:
            odd_set.add(n)
        if n % 2 == 0:
            n //= 2
        else:
            n = 3 * n + 1
    odd_set.add(1)
    return sorted(odd_set)


def get_closest_vowel(word):
    vowels = set("aeiouAEIOU")
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


# Note: the prompt supplies a helper, def encode_cyclic(s); per instructions only
# decode_cyclic is written here and that helper is not redefined.
def decode_cyclic(s: str):
    groups = [s[3 * i:min(3 * (i + 1), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    expr = str(operand[0]) + "".join(" {} {}".format(op, v) for op, v in zip(operator, operand[1:]))
    # operands are non-negative integers and operators are the basic algebra ones,
    # so evaluating the built expression is safe
    return eval(expr)


def fib4(n):
    if n < 0 or n > 10**6:
        raise ValueError("n out of range")
    base = [0, 0, 2, 0]
    if n <= 3:
        return base[n]
    a, b, c, d = base[0], base[1], base[2], base[3]
    for _ in range(4, n + 1):
        a, b, c, d = b, c, d, a + b + c + d
    return d


def string_to_md5(text: str) -> str:
    import hashlib

    if text == "":
        return None
    md5_hash = hashlib.md5()
    md5_hash.update(text.encode("utf-8"))
    return md5_hash.hexdigest()


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
        magnitude_sum += abs(x)
        if x > 0:
            s = 1
        elif x < 0:
            s = -1
        else:
            s = 0
        sign_product *= s
    return magnitude_sum * sign_product


def valid_date(date):
    if not date or len(date) != 10:
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
    max_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not (1 <= dd <= max_days[mm - 1]):
        return False
    return True


def fibfib(n):
    base = [0, 0, 1]
    if n < 3:
        return base[n]
    a, b, c = base[0], base[1], base[2]
    for _ in range(3, n + 1):
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

    a, b = lst[0], lst[1]
    if is_good(a + b) or is_good(b + a):
        return "Yes"
    else:
        return "No"


def parse_music(music_string: str) -> List[int]:
    beats = {"o": 4, "o|": 2, ".|": 1}
    return [beats[note] for note in music_string.split()]


def filter_integers(values):
    return [v for v in values if type(v) is int]


def digits(n):
    product = 0
    found_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            if not found_odd:
                product = d
                found_odd = True
            else:
                product *= d
    return product
