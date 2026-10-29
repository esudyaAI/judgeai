"""Facts for ч. 1 ст. 58 УК РФ read from the verdict text by regex (T13).

Each reader returns the value and the quote it rests on, or (None, "") when the text does not
say it plainly; nothing is guessed. The sex of the convicted person is taken from grammatical
forms that refer to him or her; previous imprisonment from explicit phrases of the introductory
part; the regime from the last mention of a correctional institution (the operative part comes
last).
"""

import re

from legal_core.rules.art58 import Regime

_REGIME = re.compile(
    r"колони[июя]-поселени[июея]"
    r"|исправительн\w*\s+колони\w*\s+(?P<kind>общего|строгого|особого)\s+режима",
    re.IGNORECASE,
)
_KINDS = {"общего": Regime.GENERAL, "строгого": Regime.STRICT, "особого": Regime.SPECIAL}

_FEMALE = re.compile(
    r"\b(?:подсудим(?:ая|ой|ую)|осужд[её]нн(?:ая|ой|ую)|гражданк[аеуи]|виновн(?:ой|ая))\b",
    re.IGNORECASE,
)
_MALE = re.compile(
    r"\b(?:подсудим(?:ый|ого|ому|ым)|осужд[её]нн(?:ый|ого|ому|ым)|гражданин(?:а|у|ом)?|виновн(?:ым|ый))\b",
    re.IGNORECASE,
)

_NOT_SERVED = re.compile(
    r"(?:ранее\s+не\s+отбывавш\w*|не\s+отбывал\w*)\s+(?:наказани\w+\s+в\s+виде\s+)?лишени\w+\s+свободы",
    re.IGNORECASE,
)
# "Освобождён по отбытии наказания" alone is not enough: it follows non-custodial
# punishments too. Only phrases that name imprisonment or a place of it count.
_SERVED = re.compile(
    r"(?<!не\s)(?:ранее\s+отбывавш\w*|отбывал\w*)\s+(?:наказани\w+\s+в\s+виде\s+)?"
    r"(?:реальн\w+\s+)?лишени\w+\s+свободы"
    r"|освобожд[её]н\w*\s+(?:\S+\s+){0,4}?из\s+(?:мест\s+лишения\s+свободы"
    r"|исправительной\s+колонии|ИК-?\d*)",
    re.IGNORECASE,
)
_NOT_CONVICTED = re.compile(r"ранее\s+не\s+судим\w*", re.IGNORECASE)


def read_regime(text: str) -> tuple[Regime | None, str]:
    matches = list(_REGIME.finditer(text))
    if not matches:
        return None, ""
    last = matches[-1]
    kind = last.group("kind")
    regime = _KINDS[kind.lower()] if kind else Regime.SETTLEMENT
    return regime, last.group(0)


def read_male(text: str) -> tuple[bool | None, str]:
    """True for a man, False for a woman; None when the forms are absent or mixed."""

    def forms(pattern):
        return [
            m[0]
            for m in pattern.finditer(text)
            if not (
                m[0].lower().startswith("граждан")
                and re.search(r"свидетел\w*\s+$", text[max(0, m.start() - 25) : m.start()], re.I)
            )
        ]

    female = forms(_FEMALE)
    male = forms(_MALE)
    if female and not male:
        return False, female[0]
    if male and not female:
        return True, male[0]
    return None, ""


def read_served_before(text: str) -> tuple[bool | None, str]:
    """Whether the convicted person served imprisonment before, by explicit phrases only."""
    negative = _NOT_SERVED.search(text)
    positives = [
        m
        for m in _SERVED.finditer(text)
        if not re.search(r"не\s+$", text[max(0, m.start() - 4) : m.start()], re.I)
    ]
    positive = positives[0] if positives else None
    released = re.search(
        r"освобожд[её]н\w*[^.;]{0,100}по\s+отбытии[^.;]{0,60}(?:срока|наказания)", text, re.I
    )
    if released and re.search(
        r"лишени\w+\s+свободы|исправительн\w+\s+колони", released.group(), re.I
    ):
        positive = positive or released
    if negative and positive:
        return None, ""
    if negative:
        return False, negative.group(0)
    if positive:
        return True, positive.group(0)
    never = _NOT_CONVICTED.search(text)
    if never:
        return False, never.group(0)
    return None, ""
