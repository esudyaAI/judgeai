"""T45.2 — a language model may word an answer, never add a number to it.

The facts of an answer (counts, terms, shares) are counted by code. When a model rewords
them, every number of its text must be one of the numbers of the facts it was given: a
number that is not there — a recomputed term («30 месяцев» for «2 г. 6 мес.»), a rounded
mean, an invented count — makes the wording unusable, and the answer written by code is
shown instead. Numbers spelled as words («пять приговоров») are numbers too.

Comparison is on normalised tokens: «1 159» and «1159», «2,5» and «2.5» are the same number;
«ё» is «е». The check is deliberately strict: a false refusal only costs the model's wording,
a false acceptance would put a number without a source in front of the user.
"""

import re

# A space (also no-break and narrow no-break) between digit groups of one number: «1 159».
_GROUP_SEPARATOR = re.compile(r"(?<=\d)[   ](?=\d{3}(?!\d))")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
# Cardinal numerals and fractions in their usual forms; ordinary words are not matched
# because every alternative is a whole word.
_NUMERAL_WORD = re.compile(
    r"(?<![а-я])(?:"
    r"ноль|нол[ьяю]|нул[ьяюем]|"
    r"один|одн(?:а|о|ого|ой|ому|им|ом|у|их|ими)|"
    r"дв(?:а|е|ух|ум|умя)|обо(?:их|им|ими)|оба|обе|"
    r"тр(?:и|ех|ем|емя)|четыр(?:е|ех|ем|ьмя)|"
    r"(?:пят|шест|сем|восем|девят|десят)(?:ь|и|ью)|восьм(?:и|ью)|"
    r"[а-я]+надцат(?:ь|и|ью)|"
    r"(?:двадцат|тридцат)(?:ь|и|ью)|сорок(?:а)?|"
    r"(?:пят|шест|сем|восем|девят)ьдесят|девяност(?:о|а)|"
    r"сто|ста|сот|двест[иа]|(?:трист|четырест)(?:а|ам)|(?:пят|шест|сем|восем|девят)ьсот|"
    r"тысяч[аиуье]?|тысяч(?:ам|ами|ах)|миллион(?:а|ов)?|"
    r"полтор(?:а|ы)|полутора|половин(?:а|ы|у|е|ой)|"
    r"трет(?:ь|и|ью)|четверт(?:ь|и|ью)"
    r")(?![а-я])"
)


def _normalise(text: str) -> str:
    return _GROUP_SEPARATOR.sub("", text.lower().replace("ё", "е"))


def number_tokens(text: str) -> frozenset[str]:
    """Every number of the text, as digits («2.5») or as a numeral word («пять»)."""
    normalised = _normalise(text)
    digits = {token.replace(",", ".") for token in _DIGITS.findall(normalised)}
    words = set(_NUMERAL_WORD.findall(normalised))
    return frozenset(digits | words)


def unsupported_numbers(answer: str, facts: str) -> frozenset[str]:
    """Numbers of the answer that are not numbers of the facts; empty — the answer may stand."""
    return number_tokens(answer) - number_tokens(facts)
