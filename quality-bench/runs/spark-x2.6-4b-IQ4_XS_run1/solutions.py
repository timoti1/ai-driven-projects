def reverse_delete(s, c):
    for ch in c:
        s = s.replace(ch, "")
    return (s, s == s[::-1])


def filter_by_prefix(strings, prefix):
    return [s for s in strings if s.startswith(prefix)]


def separate_paren_groups(paren_string):
    paren_string = paren_string.replace(" ", "")
    groups = []
    current = ""
    level = 0
    for char in paren_string:
        if char == "(":
            level += 1
            current += char
        elif char == ")":
            level -= 1
            current += char
        if level == 0:
            groups.append(current)
            current = ""
    return groups


def strlen(string):
    return len(string)


def sorted_list_sum(lst):
    return sorted([s for s in lst if len(s) % 2 == 0], key=lambda s: (len(s), s))


def sum_product(numbers):
    s = sum(numbers)
    p = 1
    for n in numbers:
        p *= n
    return (s, p)


def rescale_to_unit(numbers):
    min_v = min(numbers)
    max_v = max(numbers)
    return [(v - min_v) / (max_v - min_v) for v in numbers]


def factorize(n):
    factors = []
    i = 2
    while i * i <= n:
        while n % i == 0:
            factors.append(i)
            n //= i
        i += 1
    if n > 1:
        factors.append(n)
    return factors


def next_smallest(lst):
    if len(lst) < 2:
        return None
    first = min(lst)
    second = None
    for x in lst:
        if x != first:
            second = min(second, x) if second is not None else x
    return second


def sum_to_n(n):
    return n * (n + 1) // 2


def mean_absolute_deviation(numbers):
    mean = sum(numbers) / len(numbers)
    return sum(abs(x - mean) for x in numbers) / len(numbers)


def filter_by_substring(strings, substring):
    return [s for s in strings if substring in s]


def Strongest_Extension(class_name, extensions):
    strongest = ""
    best_strength = -float("inf")
    for ext in extensions:
        cap = sum(1 for c in ext if c.isupper())
        sm = sum(1 for c in ext if c.islower())
        strength = cap - sm
        if strength > best_strength:
            best_strength = strength
            strongest = ext
    return f"{class_name}.{strongest}"


def sort_array(array):
    if len(array) <= 1:
        return list(array)
    if (array[0] + array[-1]) % 2 == 1:
        return sorted(array)
    return sorted(array, reverse=True)


def get_odd_collatz(n):
    odd = []
    while n != 1:
        if n % 2 == 1:
            odd.append(n)
        n = n // 2 if n % 2 == 0 else 3 * n + 1
    odd.append(1)
    return sorted(odd)


def get_closest_vowel(word):
    vowels = "aeiou"
    result = ""
    for i in range(len(word) - 1, -1, -1):
        if word[i].lower() in vowels:
            if i > 0 and i < len(word) - 1:
                prev = word[i - 1]
                next_char = word[i + 1]
                if prev.lower() not in vowels and next_char.lower() not in vowels:
                    result = word[i]
                    break
    return result


def encode_cyclic(s):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def do_algebra(operator, operand):
    expr = operand[0]
    for i in range(len(operator)):
        expr = f"{expr} {operator[i]}{operand[i + 1]}"
    return eval(expr)


def fib4(n):
    if n < 0:
        return 0
    if n < 4:
        return [0, 0, 2, 0][n]
    return fib4(n - 1) + fib4(n - 2) + fib4(n - 3) + fib4(n - 4)


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
    if len(arr) == 0:
        return None
    product = 1
    for x in arr:
        product *= 1 if x > 0 else (-1 if x < 0 else 0)
    total = sum(abs(x) for x in arr)
    return total * product


def valid_date(date):
    if not date:
        return False
    parts = date.split("-")
    if len(parts) != 3:
        return False
    month, day, year = parts
    if not month.isdigit() or not day.isdigit() or not year.isdigit():
        return False
    month = int(month)
    day = int(day)
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    if month in (1, 3, 5, 7, 8, 10, 12):
        if day > 31:
            return False
    elif month in (4, 6, 9, 11):
        if day > 30:
            return False
    elif month == 2:
        if day > 29:
            return False
    return True


def fibfib(n):
    if n < 3:
        return [0, 0, 1][n]
    return fibfib(n - 1) + fibfib(n - 2) + fibfib(n - 3)


def count_distinct_characters(string):
    return len(set(string.upper()))


def is_equal_to_sum_even(n):
    return n % 2 == 0 and n >= 8


def match_parens(lst):
    total = 0
    for s in lst:
        total += sum(1 if c == "(" else -1 for c in s)
    if total < 0:
        return "No"
    if total % 2 != 0:
        return "No"
    return "Yes"


def parse_music(music_string):
    result = []
    for note in music_string.split(" "):
        if note == "o":
            result.append(4)
        elif note == "o|":
            result.append(2)
        elif note == ".|":
            result.append(1)
    return result


def filter_integers(values):
    return [v for v in values if isinstance(v, int)]


def digits(n):
    result = 1
    all_even = True
    for ch in str(n):
        d = int(ch)
        if d % 2 == 1:
            result *= d
            all_even = False
    return result if not all_even else 0
