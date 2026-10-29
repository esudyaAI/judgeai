# Domain Layer — ст. 66 УК РФ «Назначение наказания за неоконченное преступление».
# ч. 2: for preparation the term or amount cannot exceed one half of the maximum of the most
# severe punishment for the completed offence; ч. 3: for an attempt — three quarters.
# ч. 4: death penalty and life imprisonment are not imposed for an unfinished offence (not
# modelled here: the analysis compares terms of imprisonment).
# Пленум ВС РФ № 58 от 22.12.2015, п. 49: with recidivism one third under ч. 2 ст. 68 is taken of
# the maximum already reduced under ст. 66; the same reduced maximum bounds ч. 1 ст. 62.

from fractions import Fraction

from legal_core.entities import Unfinished

NEEDS_LEGAL_REVIEW = True
SOURCE = (
    "УК РФ ст. 66, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/ "
    "(УК РФ ред. от 04.08.2026); Пленум ВС РФ от 22.12.2015 N 58, п. 49"
)
_SHARE = {Unfinished.PREPARATION: Fraction(1, 2), Unfinished.ATTEMPT: Fraction(3, 4)}
NORMS = {Unfinished.PREPARATION: "ч. 2 ст. 66 УК РФ", Unfinished.ATTEMPT: "ч. 3 ст. 66 УК РФ"}
SHARE_WORDS = {Unfinished.PREPARATION: "половина", Unfinished.ATTEMPT: "три четверти"}


def reduced_maximum(maximum: float, stage: Unfinished | None) -> float:
    """The maximum that binds the court for this stage; the full maximum for a completed offence."""
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    if stage is None:
        return maximum
    value = Fraction(maximum).limit_denominator() * _SHARE[stage]
    return int(value) if value.denominator == 1 else float(value)
