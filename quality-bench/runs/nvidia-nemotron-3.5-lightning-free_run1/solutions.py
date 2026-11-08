from typing import List


def reverse_delete(s, c):
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    paren_string = paren_string.replace(" ", "")
    result = []
    while paren_string:
        balance = 0
        for i, ch in enumerate(paren_string):
            if ch == "(":
                balance += 1
            elif ch == ")":
                balance -= 1
            if balance == 0:
                result.append(paren_string[: i + 1])
                paren_string = paren_string[i + 1:]
                break
    return result


def strlen(string: str) -> int:
    return len(string)


def sorted_list_sum(lst):
    even_length = [s for s in lst if len(s) % 2 == 0]
    return sorted(even_length, key=lambda s: (len(s), s))


def sum_product(numbers: List[int]) -> list:
    _sum = 0
    _product = 1
    for num in numbers:
        _sum += num
        _product *= num
    return [_sum, _product]


def rescale_to_unit(numbers: List[float]) -> List[float]:
    min_val = min(numbers)
    max_val = max(numbers)
    range_val = max_val - min_val
    if range_val == 0:
        return [0.0 for _ in numbers]
    return [(x - min_val) / range_val for x in numbers]


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
    unique = sorted(set(lst))
    if len(unique) < 2:
        return None
    return unique[1]


def mean_absolute_deviation(numbers: List[float]) -> float:
    mean = sum(numbers) / len(numbers) if numbers else 0.0
    return sum(abs(x - mean) for x in numbers) / len(numbers) if numbers else 0.0


def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name: str, extensions: List[str]) -> str:
    best_strength = -999
    best_ext = extensions[0] if extensions else ""
    for ext in extensions:
        cap = sum(1 for c in ext if c.isupper())
        sm = sum(1 for c in ext if c.islower())
        strength = cap - sm
        if strength > best_strength:
            best_strength = strength
            best_ext = ext
    return "{}.{}".format(class_name, best_ext)


def sort_array(array: List[int]) -> List[int]:
    if len(array) <= 1:
        return list(array)
    if (array[0] + array[-1]) % 2 == 1:
        return sorted(array)
    else:
        return sorted(array, reverse=True)


def get_odd_collatz(n: int) -> List[int]:
    sequence = []
    current = n
    while True:
        sequence.append(current)
        if current == 1:
            break
        if current % 2 == 0:
            current = current // 2
        else:
            current = 3 * current + 1
    odd_numbers = [x for x in sequence if x % 2 == 1]
    return sorted(odd_numbers)


def get_closest_vowel(word: str) -> str:
    vowels = "aeiouAEIOU"
    consonants = "bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ"
    result = ""
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels:
            left = word[i - 1]
            right = word[i + 1]
            if left in consonants and right in consonants:
                result = word[i]
                break
    return result


def decode_cyclic(s: str) -> str:
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    decoded = []
    for group in groups:
        if len(group) == 3:
            decoded.append(group[2] + group[0:2])
        else:
            decoded.append(group)
    return "".join(decoded)


def do_algebra(operator, operand):
    expr = str(operand[0])
    for i in range(len(operator)):
        expr += operator[i] + str(operand[i + 1])
    return eval(expr)


def fib4(n: int) -> int:
    if n == 0 or n == 1 or n == 3:
        return 0
    if n == 2:
        return 2
    a, b, c, d = 0, 0, 2, 0
    for i in range(3, n):
        next_val = a + b + c + d
        a, b, c, d = b, c, d, next_val
    return d


def string_to_md5(text: str):
    import hashlib
    if text == "":
        return None
    return hashlib.md5(text.encode()).hexdigest()


def sum_to_n(n: int) -> int:
    """sum_to_n is a function that sums numbers from 1 to n.
    >>> sum_to_n(30)
    465
    >>> sum_to_n(100)
    5050
    >>> sum_to_n(5)
    15
    >>> sum_to_n(10)
    55
    >>> sum_to_n(1)
    1
    """
    return n * (n + 1) // 2

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
    total_magnitude = sum(abs(x) for x in arr)
    product_of_signs = 1
    for x in arr:
        if x > 0:
            product_of_signs *= 1
        elif x < 0:
            product_of_signs *= -1
        else:
            product_of_signs *= 0
    return total_magnitude * product_of_signs


def valid_date(date: str) -> bool:
    if not date:
        return False
    parts = date.split("-")
    if len(parts) != 3:
        return False
    mm, dd, yyyy = parts
    if len(mm) != 2 or len(dd) != 2 or len(yyyy) != 4:
        return False
    try:
        month = int(mm)
        day = int(dd)
        year = int(yyyy)
    except ValueError:
        return False
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12):
        max_day = 31
    elif month in (4, 6, 9, 11):
        max_day = 30
    else:
        max_day = 29
    if day > max_day:
        return False
    return True


def fibfib(n: int) -> int:
    if n == 0 or n == 1:
        return 0
    if n == 2:
        return 1
    a, b, c = 0, 0, 1
    for i in range(3, n + 1):
        next_val = a + b + c
        a, b, c = b, c, next_val
    return c


def count_distinct_characters(string: str) -> int:
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    if n < 8:
        return False
    if n % 2 == 0:
        return True
    return False


def match_parens(lst):
    s1, s2 = lst[0], lst[1]
    # Try both concatenation orders
    if s1 + s2:
        # Check if balanced
        balance = 0
        for ch in s1 + s2:
            if ch == "(":
                balance += 1
            elif ch == ")":
                balance -= 1
            if balance < 0:
                break
        else:
            if balance == 0:
                return "Yes"
    if s2 + s1:
        balance = 0
        for ch in s2 + s1:
            if ch == "(":
                balance += 1
            elif ch == ")":
                balance -= 1
            if balance < 0:
                break
        else:
            if balance == 0:
                return "Yes"
    return "No"


def parse_music(music_string: str) -> List[int]:
    music_string = music_string.replace(" ", "")
    result = []
    i = 0
    while i < len(music_string):
        if music_string[i] == "o":
            if i + 1 < len(music_string) and music_string[i + 1] == "|":
                result.append(2)
                i += 2
            else:
                result.append(4)
                i += 1
        elif music_string[i] == ".":
            if i + 1 < len(music_string) and music_string[i + 1] == "|":
                result.append(1)
                i += 2
            else:
                # Handle unexpected case
                i += 1
        else:
            i += 1
    return result


def filter_integers(values) -> List[int]:
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def digits(n: int) -> int:
    product = 1
    has_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            has_odd = True
    if not has_odd:
        return 0
    return product


def encode_cyclic(s: str):
    """returns encoded string by cycling groups of three characters.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # cycle elements in each group. Unless group has fewer elements than 3.
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)
