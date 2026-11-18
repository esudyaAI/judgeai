"""Period of force of a provision (T15.3, T45.9): start inclusive, end exclusive.

The period comes from the law base (`legal_provisions.effective_from`/`effective_to`). A
provision whose start is not known is never taken to be in force: the answer is unknown.
"""

from datetime import date


def in_force_on(start: date | None, end: date | None, on: date) -> bool | None:
    """Was a provision in force on `on`: start inclusive, end exclusive; unknown start -> None."""
    if end is not None and end <= on:
        return False
    if start is None:
        return None
    return start <= on


def describe_period(start: date | None, end: date | None) -> str:
    """«с 01.01.2020 до 01.01.2022» — the period as the base has it; empty when none is set."""
    words = []
    if start is not None:
        words.append(f"с {start:%d.%m.%Y}")
    if end is not None:
        words.append(f"до {end:%d.%m.%Y}")
    return " ".join(words)
