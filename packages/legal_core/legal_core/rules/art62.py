# Domain Layer — ч. 1 ст. 62 УК РФ «Назначение наказания при наличии смягчающих обстоятельств».
# With mitigating circumstances under п. «и» и (или) «к» ч. 1 ст. 61 and no aggravating
# circumstances, the term cannot exceed two thirds of the maximum of the most severe punishment
# in the sanction. Moved unchanged from src/services/sentencing.py (task T4); the text and the
# edition were not re-verified against the official source in this move.
# ч. 3: ч. 1 does not apply when the Special Part article provides for life imprisonment or the
# death penalty; the punishment is set within the sanction.
# ч. 5: a case heard under гл. 40 УПК РФ — at most two thirds of the maximum of the most severe
# punishment; in the case of ст. 226.9 УПК РФ — at most one half.
# TODO(T13/T23): the order of ч. 1, ч. 5 and ст. 66 when they coincide is not modelled; the
# procedure comes from the verdict; ч. 2 and ч. 4 (pre-trial agreement) are not modelled.
import math
import re
from collections.abc import Iterable
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art62.part1_mitigation"
RULE_KEY_PART5 = "art62.part5_procedure"
NORM_PART5 = "Наказание при особом порядке и сокращённом дознании: ч. 5 ст. 62 УК РФ"
SOURCE_PART5 = (
    "УК РФ ст. 62, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "eba3a8b2a703f3b766b7bc5394f76b42e6394c34/ (УК РФ ред. от 04.08.2026, сверено 08.11.2026)"
)


class ProcedureKind(StrEnum):
    """Procedure the case was heard under, as established from the verdict."""

    GENERAL = "general"
    CHAPTER_40 = "chapter_40"  # гл. 40 УПК РФ
    ART_226_9 = "art_226_9"  # ст. 226.9 УПК РФ
    UNKNOWN = "unknown"


_PROCEDURE_FRACTION = {ProcedureKind.CHAPTER_40: (2, 3), ProcedureKind.ART_226_9: (1, 2)}
_PROCEDURE_SHARE = {ProcedureKind.CHAPTER_40: "двух третей", ProcedureKind.ART_226_9: "половины"}

_PART1_ART61 = re.compile(r"ч\.?\s*1\s*ст\.?\s*61(?!\d)(?!\.\d)", re.IGNORECASE)
_ITEM_LETTER = re.compile(r"«\s*([а-яё])\s*»", re.IGNORECASE)
_PART1_LETTERS = {"и", "к"}


def _cited_art61_part1_items(norm: str) -> set[str]:
    """Item letters of ч. 1 ст. 61 cited in a norm, e.g. 'п. «г», «и» ч. 1 ст. 61' -> {'г','и'}."""
    match = _PART1_ART61.search(norm)
    if not match:
        return set()
    return {letter.lower() for letter in _ITEM_LETTER.findall(norm[: match.start()])}


def has_part1_mitigation(mitigating_norms: Iterable[str]) -> bool:
    """Does any mitigating circumstance cite п. «и» or «к» ч. 1 ст. 61?"""
    return any(_cited_art61_part1_items(norm) & _PART1_LETTERS for norm in mitigating_norms)


def part1_limit_months(
    sanction_max_months: int,
    mitigating_norms: Iterable[str],
    *,
    has_aggravating: bool,
    sanction_has_life_or_death: bool = False,
) -> int | None:
    """Upper limit in whole months, or None when ч. 1 ст. 62 does not apply (incl. ч. 3).

    Rounded down: rounding up could produce a term above the statutory two thirds.
    """
    if sanction_max_months <= 0 or has_aggravating or sanction_has_life_or_death:
        return None
    if not has_part1_mitigation(mitigating_norms):
        return None
    return math.floor(sanction_max_months * 2 / 3)


def procedure_maximum(sanction_max_months: int, procedure: ProcedureKind) -> int | None:
    """Maximum in whole months under ч. 5, or None when the procedure is unknown.

    Rounded down, as a higher whole-month term would exceed the statutory share.
    """
    if sanction_max_months <= 0:
        raise ValueError("sanction maximum must be positive")
    if procedure is ProcedureKind.UNKNOWN:
        return None
    if procedure is ProcedureKind.GENERAL:
        return sanction_max_months
    numerator, denominator = _PROCEDURE_FRACTION[procedure]
    return math.floor(sanction_max_months * numerator / denominator)


def check_procedure_term(
    *,
    procedure: ProcedureKind,
    imposed_months: int | None,
    most_severe_max_months: int | None,
    imposed_most_severe_kind: bool,
) -> CheckResult:
    """Candidate check of the imposed punishment against ч. 5 ст. 62 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            NORM_PART5, status, why, SOURCE_PART5, NEEDS_LEGAL_REVIEW, RULE_KEY_PART5
        )

    if procedure is ProcedureKind.GENERAL:
        return result(CheckStatus.OK, "Общий порядок — ч. 5 ст. 62 УК РФ не применяется.")
    if procedure is ProcedureKind.UNKNOWN:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Порядок рассмотрения дела не установлен — ч. 5 ст. 62 УК РФ не проверена.",
        )
    if not imposed_most_severe_kind:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Назначен менее строгий вид наказания, чем наиболее строгий в санкции, — предел "
            "ч. 5 ст. 62 УК РФ для него не проверяется.",
        )
    if (
        imposed_months is None
        or imposed_months <= 0
        or most_severe_max_months is None
        or most_severe_max_months <= 0
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Срок наказания или максимум санкции не определены."
        )
    limit = procedure_maximum(most_severe_max_months, procedure)
    share = _PROCEDURE_SHARE[procedure]
    if imposed_months <= limit:
        return result(
            CheckStatus.OK,
            f"Назначено {imposed_months} мес. — не более {share} максимума "
            f"({limit} из {most_severe_max_months} мес., ч. 5 ст. 62 УК РФ).",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"Назначено {imposed_months} мес. — больше {share} максимума ({limit} из "
        f"{most_severe_max_months} мес.), ч. 5 ст. 62 УК РФ.",
    )
