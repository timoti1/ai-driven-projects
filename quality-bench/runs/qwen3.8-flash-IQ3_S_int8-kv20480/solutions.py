from typing import List


def reverse_delete(s, c):
    """Task
    We are given two strings s and c, you have to deleted all the characters in s that are equal to any character in c
    then check if the result string is palindrome.
    """
    result = "".join(ch for ch in s if ch not in c)
    return (result, result == result[::-1])


def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:
    """ Filter an input list of strings only for ones that start with a given prefix.
    >>> filter_by_prefix([], 'a')
    []
    >>> filter_by_prefix(['abc', 'bcd', 'cde', 'array'], 'a')
    ['abc', 'array']
    """
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string: str) -> List[str]:
    """ Input to this function is a string containing multiple groups of nested parentheses.
    >>> separate_paren_groups('( ) (( )) (( )( ))')
    ['()', '(())', '(()())']
    """
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
                result.append("".join(current))
                current = []
    return result


def strlen(string: str) -> int:
    """ Return length of given string
    >>> strlen('')
    0
    >>> strlen('abc')
    3
    """
    return len(string)


def sorted_list_sum(lst):
    """Delete odd-length strings, return the list sorted by length then alphabetically."""
    kept = [w for w in lst if len(w) % 2 == 0]
    return sorted(kept, key=lambda w: (len(w), w))


def sum_product(numbers: List[int]):
    """ For a given list of integers, return a tuple consisting of a sum and a product.
    >>> sum_product([])
    (0, 1)
    >>> sum_product([1, 2, 3, 4])
    (10, 24)
    """
    total = 0
    product = 1
    for n in numbers:
        total += n
        product *= n
    return (total, product)


def rescale_to_unit(numbers: List[float]) -> List[float]:
    """ Apply a linear transform so the smallest becomes 0 and the largest becomes 1.
    >>> rescale_to_unit([1.0, 2.0, 3.0, 4.0, 5.0])
    [0.0, 0.25, 0.5, 0.75, 1.0]
    """
    mn = min(numbers)
    mx = max(numbers)
    return [(x - mn) / (mx - mn) for x in numbers]


def factorize(n: int) -> List[int]:
    """ Return list of prime factors of given integer from smallest to largest.
    >>> factorize(8)
    [2, 2, 2]
    >>> factorize(25)
    [5, 5]
    >>> factorize(70)
    [2, 5, 7]
    """
    factors = []
    d = 2
    while n > 1:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    return factors


def next_smallest(lst):
    """Return the 2nd smallest element of the list, None if there is no such element."""
    unique = sorted(set(lst))
    if len(unique) < 2:
        return None
    return unique[1]


def sum_to_n(n: int):
    """sum_to_n is a function that sums numbers from 1 to n.
    >>> sum_to_n(30)
    465
    >>> sum_to_n(100)
    5050
    >>> sum_to_n(5)
    15
    """
    return n * (n + 1) // 2


def mean_absolute_deviation(numbers: List[float]) -> float:
    """ Mean Absolute Deviation around the mean of the dataset.
    >>> mean_absolute_deviation([1.0, 2.0, 3.0, 4.0])
    1.0
    """
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings: List[str], substring: str) -> List[str]:
    """ Filter an input list of strings only for ones that contain given substring.
    >>> filter_by_substring(['abc', 'bacd', 'cde', 'array'], 'a')
    ['abc', 'bacd', 'array']
    """
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    """Return ClassName.StrongestExtensionName (strength = CAP - SM, first wins ties)."""
    def strength(ext):
        cap = sum(1 for ch in ext if ch.isupper())
        small = sum(1 for ch in ext if ch.islower())
        return cap - small

    best = max(extensions, key=strength)
    return class_name + "." + best


def sort_array(array):
    """Sort ascending if sum(first, last) is odd, descending if even; copy only."""
    if not array:
        return []
    if (array[0] + array[-1]) % 2 == 0:
        return sorted(array, reverse=True)
    return sorted(array)


def get_odd_collatz(n):
    """Return a sorted list of the odd numbers in the collatz sequence of n."""
    odds = []
    while n != 1:
        if n % 2 == 1:
            odds.append(n)
            n = 3 * n + 1
        else:
            n = n // 2
    odds.append(1)
    return sorted(odds)


def get_closest_vowel(word):
    """Closest vowel (from the right) that stands between two consonants."""
    vowels = "aeiouAEIOU"
    for i in range(len(word) - 2, 0, -1):
        if word[i] in vowels and word[i - 1] not in vowels and word[i + 1] not in vowels:
            return word[i]
    return ""


def decode_cyclic(s: str):
    """
    takes as input string encoded with encode_cyclic function. Returns decoded string.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # reverse the cycle (right shift) in each full group.
    groups = [(group[-1] + group[:-1]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    """Build the algebraic expression from operator and operand lists and evaluate it."""
    expression = str(operand[0])
    for op, num in zip(operator, operand[1:]):
        expression += op + str(num)
    return eval(expression)


def fib4(n: int):
    """ n-th element of the fib4 sequence, computed iteratively.
    >>> fib4(5)
    4
    >>> fib4(6)
    8
    >>> fib4(7)
    14
    """
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
    """MD5 hash of 'text' as a hex string; None for the empty string.
    >>> string_to_md5('Hello world') == '3e25960a79dbc69b674cd4ec67a72c62'
    True
    """
    import hashlib

    if not text:
        return None
    return hashlib.md5(text.encode()).hexdigest()


def below_zero(operations: List[int]) -> bool:
    """True if the balance ever falls below zero, else False.
    >>> below_zero([1, 2, 3])
    False
    >>> below_zero([1, 2, -4, 5])
    True
    """
    balance = 0
    for op in operations:
        balance += op
        if balance < 0:
            return True
    return False


def prod_signs(arr):
    """Sum of magnitudes * product of signs; None for empty arr."""
    if not arr:
        return None
    sign_product = 1
    magnitude_sum = 0
    for x in arr:
        if x == 0:
            sign_product = 0
        elif x < 0:
            sign_product *= -1
        magnitude_sum += abs(x)
    return magnitude_sum * sign_product


def valid_date(date):
    """Validate a 'mm-dd-yyyy' date string."""
    if not date:
        return False
    parts = date.split("-")
    if len(parts) != 3:
        return False
    month, day, year = parts
    if not (month.isdigit() and day.isdigit() and year.isdigit()):
        return False
    month, day = int(month), int(day)
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12) and day > 31:
        return False
    if month in (4, 6, 9, 11) and day > 30:
        return False
    if month == 2 and day > 29:
        return False
    return True


def fibfib(n: int):
    """ n-th element of the fibfib sequence, computed iteratively.
    >>> fibfib(1)
    0
    >>> fibfib(5)
    4
    >>> fibfib(8)
    24
    """
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
    """ Number of distinct characters (case-insensitive).
    >>> count_distinct_characters('xyzXYZ')
    3
    >>> count_distinct_characters('Jerry')
    4
    """
    return len(set(string.lower()))


def is_equal_to_sum_even(n):
    """True if n is the sum of exactly 4 positive even numbers."""
    return n % 2 == 0 and n >= 8


def match_parens(lst):
    """'Yes' if the two strings can be concatenated (in some order) into a balanced string."""
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
    return 'Yes' if good(a + b) or good(b + a) else 'No'


def parse_music(music_string: str) -> List[int]:
    """ Parse musical notes into beat lengths.
    >>> parse_music('o o| .| o| o| .| .| .| .| o o')
    [4, 2, 1, 2, 2, 1, 1, 1, 1, 4, 4]
    """
    legend = {'o': 4, 'o|': 2, '.|': 1}
    return [legend[note] for note in music_string.split()]


def filter_integers(values: List) -> List[int]:
    """ Filter given list of any python values only for integers
    >>> filter_integers(['a', 3.14, 5])
    [5]
    >>> filter_integers([1, 2, 3, 'abc', {}, []])
    [1, 2, 3]
    """
    return [x for x in values if isinstance(x, int)]


def digits(n):
    """Product of the odd digits of n; 0 if all digits are even."""
    product = 1
    seen_odd = False
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            product *= d
            seen_odd = True
    return product if seen_odd else 0


def encode_cyclic(s: str):
    """
    returns encoded string by cycling groups of three characters.
    """
    # split string to groups. Each of length 3.
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    # cycle elements in each group. Unless group has fewer elements than 3.
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)
