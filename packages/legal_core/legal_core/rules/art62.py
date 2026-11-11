# Domain Layer — ч. 1 ст. 62 УК РФ «Назначение наказания при наличии смягчающих обстоятельств».
# With mitigating circumstances under п. «и» и (или) «к» ч. 1 ст. 61 and no aggravating
# circumstances, the term cannot exceed two thirds of the maximum of the most severe punishment
# in the sanction. Moved unchanged from src/services/sentencing.py (task T4); the text and the
# edition were not re-verified against the official source in this move.
# ч. 3: ч. 1 does not apply when the Special Part article provides for life imprisonment or the
# death penalty; the punishment is set within the sanction.
# ч. 5: a case heard under гл. 40 УПК РФ — at most two thirds of the maximum of the most severe
# punishment; in the case of ст. 226.9 УПК РФ — at most one half.
# ч. 2 and ч. 4 (pre-trial cooperation agreement) — check_pretrial_agreement_term below.
# TODO(T13/T23): the order of ч. 1, ч. 2, ч. 4, ч. 5 and ст. 66 when they coincide is not
# modelled; the procedure and the agreement come from the verdict.
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
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


# ч. 2 ст. 62: a pre-trial cooperation agreement, mitigation under п. «и» ч. 1 ст. 61 and no
# aggravating circumstances — at most one half of the maximum of the most severe punishment.
# ч. 4 ст. 62: a pre-trial cooperation agreement and a sanction with life imprisonment or the death
# penalty — these kinds are not applied, and the term is at most two thirds of the maximum term of
# imprisonment in the sanction (no condition on mitigating or aggravating circumstances).
# Text compared verbatim with the official pravo.gov.ru export in the local legal library
# (legal_provisions, article.62, edition in force by ФЗ от 29.06.2009 N 141-ФЗ). Whether the
# agreement counts (obligations fulfilled, case heard under гл. 40.1 УПК РФ) is decided by the
# caller — an open question for T23 together with the order of ч. 2/4 and ч. 5, ст. 66.
AGREEMENT_RULE_KEY = "art62.pretrial_agreement"
AGREEMENT_NORM = "Досудебное соглашение о сотрудничестве: ч. 2 и ч. 4 ст. 62 УК РФ"
AGREEMENT_SOURCE = (
    "УК РФ ст. 62 ч. 2, ч. 4 (в ред. ФЗ от 29.06.2009 N 141-ФЗ) — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, sha256 "
    "0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (статус unreviewed)"
)


@dataclass(frozen=True)
class PretrialAgreementFacts:
    """Facts for ч. 2/4 ст. 62; ``None`` — the fact was not extracted.

    ``agreement`` — a pre-trial cooperation agreement applies to the case.
    ``item_i_mitigation`` — mitigation under п. «и» ч. 1 ст. 61 is established (ч. 2).
    ``has_aggravating`` — any aggravating circumstance is established (ч. 2).
    ``sanction_has_life_or_death`` — the article provides life imprisonment or death (ч. 4).
    """

    agreement: bool | None
    item_i_mitigation: bool | None
    has_aggravating: bool | None
    sanction_has_life_or_death: bool | None


@dataclass(frozen=True)
class DraftAgreementTerm:
    """The punishment in the draft for this offence; ``None`` — not extracted.

    ``imposed_most_severe_kind`` — the imposed kind is the base of the limit: the most severe kind
    of the sanction (ч. 2) or imprisonment (ч. 4). ``limit_base_max_months`` — its maximum.
    """

    imposed_life_or_death: bool | None
    imposed_most_severe_kind: bool | None
    imposed_months: int | None
    limit_base_max_months: int | None


def agreement_maximum(base_max_months: int, *, sanction_has_life_or_death: bool) -> int:
    """Maximum in whole months: one half (ч. 2) or two thirds (ч. 4), rounded down."""
    if base_max_months <= 0:
        raise ValueError("sanction maximum must be positive")
    if sanction_has_life_or_death:
        return math.floor(base_max_months * 2 / 3)
    return math.floor(base_max_months / 2)


def check_pretrial_agreement_term(
    facts: PretrialAgreementFacts, draft: DraftAgreementTerm
) -> CheckResult:
    """Candidate check of the imposed punishment against ч. 2 and ч. 4 ст. 62 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            AGREEMENT_NORM,
            status,
            why,
            AGREEMENT_SOURCE,
            NEEDS_LEGAL_REVIEW,
            AGREEMENT_RULE_KEY,
        )

    if draft.imposed_months is not None and draft.imposed_months < 0:
        raise ValueError("imposed term must not be negative")
    if draft.limit_base_max_months is not None and draft.limit_base_max_months <= 0:
        raise ValueError("sanction maximum must be positive")
    if facts.agreement is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, заключалось ли досудебное соглашение о сотрудничестве, — "
            "ч. 2 и ч. 4 ст. 62 УК РФ не проверены.",
        )
    if not facts.agreement:
        return result(
            CheckStatus.OK,
            "Досудебное соглашение о сотрудничестве не заключалось — ч. 2 и ч. 4 ст. 62 УК РФ "
            "не применяются.",
        )
    if facts.sanction_has_life_or_death is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, предусматривает ли санкция пожизненное лишение свободы или смертную "
            "казнь, — не определено, применяется ч. 2 или ч. 4 ст. 62 УК РФ.",
        )
    if facts.sanction_has_life_or_death:
        part, share = "ч. 4 ст. 62", "двух третей"
        if draft.imposed_life_or_death:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                "При досудебном соглашении о сотрудничестве пожизненное лишение свободы и "
                "смертная казнь не применяются (ч. 4 ст. 62 УК РФ).",
            )
        if draft.imposed_life_or_death is None:
            return result(
                CheckStatus.INSUFFICIENT_DATA,
                "Не установлено, назначено ли пожизненное лишение свободы, — ч. 4 ст. 62 УК РФ "
                "не проверена.",
            )
    else:
        part, share = "ч. 2 ст. 62", "половины"
        if facts.item_i_mitigation is False or facts.has_aggravating is True:
            return result(
                CheckStatus.OK,
                "Нет смягчающего обстоятельства п. «и» ч. 1 ст. 61 или есть отягчающие — "
                "ч. 2 ст. 62 УК РФ не применяется.",
            )
        if facts.item_i_mitigation is None or facts.has_aggravating is None:
            return result(
                CheckStatus.INSUFFICIENT_DATA,
                "Не установлены смягчающее обстоятельство п. «и» ч. 1 ст. 61 или отсутствие "
                "отягчающих — ч. 2 ст. 62 УК РФ не проверена.",
            )
    if draft.imposed_most_severe_kind is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            f"Вид назначенного наказания не установлен — предел {part} УК РФ не проверен.",
        )
    if not draft.imposed_most_severe_kind:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            f"Назначен менее строгий вид наказания — предел {part} УК РФ для него не проверяется.",
        )
    if draft.imposed_months is None or draft.limit_base_max_months is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Срок наказания или максимум санкции не определены."
        )
    limit = agreement_maximum(
        draft.limit_base_max_months, sanction_has_life_or_death=facts.sanction_has_life_or_death
    )
    numbers = f"{limit} из {draft.limit_base_max_months} мес."
    if draft.imposed_months <= limit:
        return result(
            CheckStatus.OK,
            f"Назначено {draft.imposed_months} мес. — не более {share} максимума ({numbers}, "
            f"{part} УК РФ).",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"Назначено {draft.imposed_months} мес. — больше {share} максимума ({numbers}), "
        f"{part} УК РФ.",
    )
