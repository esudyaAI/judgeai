# Domain Layer — ч. 3 и ч. 4 ст. 70 УК РФ «Назначение наказания по совокупности приговоров»
# (окончательное наказание в виде лишения свободы): ч. 3 — ред. ФЗ от 05.05.2014 N 130-ФЗ
# (не более тридцати лет, кроме случаев ч. 5 ст. 56 — тогда не более тридцати пяти лет);
# ч. 4 — окончательное наказание должно быть больше и наказания по последнему приговору, и
# неотбытой части наказания по предыдущему приговору («больше» — строго).
# Перечень статей ч. 5 ст. 56 — данные (ред. ФЗ N 375-ФЗ, N 46-ФЗ зависят от даты деяния),
# поэтому отнесение передаёт вызывающий. Сроки — в месяцах лишения свободы; приведение других
# видов к лишению свободы (ст. 71) и неотбытой части в днях вызывающий выполняет сам.
# Известное нарушение выдаётся, даже если другие факты не установлены; иначе неизвестный
# значимый факт → «недостаточно данных». Толкование сверяется в T23.
# Ч. 1 и ч. 2 — отдельное правило `art70.attachment` ниже: окончательное наказание не больше
# суммы наказания по последнему приговору и неотбытой части (при полном присоединении — равно
# ей, при частичном — меньше); менее строгий вид — не больше максимума Общей части (данные,
# передаёт вызывающий).
# TODO(T4/T23): ч. 5 (дополнительные наказания по ч. 4 ст. 69) не смоделирована.
from dataclasses import dataclass
from enum import Enum

from legal_core.checks import CheckResult, CheckStatus

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art70.cumulative_sentences"
NORM = "Совокупность приговоров: ч. 3 и ч. 4 ст. 70 УК РФ (лишение свободы)"
SOURCE = (
    "УК РФ ст. 70, ч. 3 (ред. ФЗ от 05.05.2014 N 130-ФЗ) и ч. 4; ст. 56, ч. 5 (ред. ФЗ от "
    "01.04.2019 N 46-ФЗ) — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd="
    "102041891&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde1"
    "7734e63735b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23)"
)

_THIRTY_YEARS_MONTHS = 360
_THIRTY_FIVE_YEARS_MONTHS = 420


@dataclass(frozen=True)
class SentencesCumulationFacts:
    """Facts of the case; None means the fact is not extracted.

    new_sentence_months — imprisonment imposed by the last sentence (for several new offences —
    after ст. 69); unserved_months — unserved part of the previous sentence; art56_part5 — at
    least one offence falls under the list of ч. 5 ст. 56 in the applicable edition.
    """

    new_sentence_months: int | None
    unserved_months: int | None
    art56_part5: bool | None


@dataclass(frozen=True)
class DraftCumulativeSentence:
    """What the draft imposes; None means not extracted."""

    by_cumulation: bool | None
    final_months: int | None
    life_imprisonment: bool = False


def cumulative_maximum_months(art56_part5: bool | None) -> int | None:
    """Ч. 3 ст. 70: thirty years, or thirty-five under ч. 5 ст. 56; None — not established."""
    if art56_part5 is None:
        return None
    return _THIRTY_FIVE_YEARS_MONTHS if art56_part5 else _THIRTY_YEARS_MONTHS


def _result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)


def _reject_negative(*terms: int | None) -> None:
    if any(term is not None and term < 0 for term in terms):
        raise ValueError("Срок не может быть отрицательным.")


def _limit_finding(final: int, art56_part5: bool | None) -> tuple[str | None, str | None]:
    """(violation, unknown) for ч. 3 ст. 70."""
    if final <= _THIRTY_YEARS_MONTHS:
        return None, None
    limit = cumulative_maximum_months(art56_part5)
    if limit is None and final <= _THIRTY_FIVE_YEARS_MONTHS:
        return None, "Не установлено, относится ли преступление к перечню ч. 5 ст. 56 УК РФ."
    if limit is not None and final <= limit:
        return None, None
    years = "тридцати пяти" if art56_part5 is not False else "тридцати"
    return (
        f"Окончательное лишение свободы {final} мес. превышает {years} лет (ч. 3 ст. 70 УК РФ).",
        None,
    )


def _greater_finding(final: int, other: int | None, what: str) -> tuple[str | None, str | None]:
    """(violation, unknown) for one comparison of ч. 4 ст. 70."""
    if other is None:
        return None, f"Не установлен срок {what}."
    if final > other:
        return None, None
    return (
        f"Окончательное наказание {final} мес. должно быть больше {what} ({other} мес., "
        "ч. 4 ст. 70 УК РФ).",
        None,
    )


def check_cumulative_sentences(
    facts: SentencesCumulationFacts, draft: DraftCumulativeSentence
) -> CheckResult:
    _reject_negative(facts.new_sentence_months, facts.unserved_months, draft.final_months)
    if draft.by_cumulation is False:
        return _result(CheckStatus.OK, "Наказание по совокупности приговоров не назначается.")
    if draft.by_cumulation is None:
        return _result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначается ли наказание по совокупности приговоров.",
        )
    if draft.life_imprisonment:
        return _result(
            CheckStatus.INSUFFICIENT_DATA,
            "Назначено пожизненное лишение свободы: пределы ч. 3 и ч. 4 ст. 70 УК РФ "
            "в месяцах не вычисляются.",
        )
    final = draft.final_months
    if final is None:
        return _result(
            CheckStatus.INSUFFICIENT_DATA,
            "В проекте не установлен срок окончательного лишения свободы.",
        )
    findings = [
        _limit_finding(final, facts.art56_part5),
        _greater_finding(final, facts.new_sentence_months, "наказания по последнему приговору"),
        _greater_finding(
            final, facts.unserved_months, "неотбытой части наказания по предыдущему приговору"
        ),
    ]
    violations = [violation for violation, _ in findings if violation]
    if violations:
        return _result(CheckStatus.POSSIBLE_VIOLATION, " ".join(violations))
    unknown = [gap for _, gap in findings if gap]
    if unknown:
        return _result(CheckStatus.INSUFFICIENT_DATA, " ".join(unknown))
    return _result(
        CheckStatus.OK, "Окончательное наказание соответствует ч. 3 и ч. 4 ст. 70 УК РФ."
    )


# --- ч. 1 и ч. 2 ст. 70 УК РФ: присоединение неотбытой части и менее строгие виды ---

ATTACHMENT_RULE_KEY = "art70.attachment"
ATTACHMENT_NORM = (
    "Совокупность приговоров: ч. 1 и ч. 2 ст. 70 УК РФ (присоединение неотбытой части, "
    "менее строгие виды)"
)
ATTACHMENT_SOURCE = (
    "УК РФ ст. 70, ч. 1 и ч. 2 — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd="
    "102041891&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde1"
    "7734e63735b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23)"
)


class AttachmentMethod(Enum):
    """How the unserved part is attached under ч. 1 ст. 70 («частично или полностью»)."""

    PARTIAL = "partial"
    FULL = "full"


@dataclass(frozen=True)
class DraftSentenceAttachment:
    """What the draft imposes; None means not extracted.

    final_term — the final punishment in the same units as the terms of the facts (the caller
    converts kinds under ст. 71); imprisonment — whether the final punishment is imprisonment;
    general_part_maximum — maximum of that less severe kind under the General Part (data passed
    by the caller, only for ч. 2).
    """

    by_cumulation: bool | None
    method: AttachmentMethod | None
    final_term: int | None
    imprisonment: bool | None
    general_part_maximum: int | None = None
    life_imprisonment: bool = False


def _attachment_result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(
        ATTACHMENT_NORM, status, why, ATTACHMENT_SOURCE, NEEDS_LEGAL_REVIEW, ATTACHMENT_RULE_KEY
    )


def _sum_finding(
    final: int, facts: SentencesCumulationFacts, method: AttachmentMethod | None
) -> tuple[str | None, str | None]:
    """(violation, unknown) for ч. 1 ст. 70: the final term cannot exceed new + unserved."""
    missing = [
        what
        for what, term in (
            ("наказания по последнему приговору", facts.new_sentence_months),
            ("неотбытой части наказания по предыдущему приговору", facts.unserved_months),
        )
        if term is None
    ]
    if missing:
        return None, "Не установлен срок " + " и ".join(missing) + "."
    total = facts.new_sentence_months + facts.unserved_months
    if final > total:
        return (
            f"Окончательное наказание {final} мес. больше суммы наказания по последнему "
            f"приговору и неотбытой части ({total} мес.): присоединяется не более неотбытой "
            "части (ч. 1 ст. 70 УК РФ).",
            None,
        )
    if method is AttachmentMethod.FULL and final < total:
        return (
            f"Неотбытая часть присоединена полностью, но окончательное наказание {final} мес. "
            f"меньше суммы {total} мес. (ч. 1 ст. 70 УК РФ).",
            None,
        )
    if method is AttachmentMethod.PARTIAL and final == total:
        return (
            f"Неотбытая часть присоединена частично, но окончательное наказание {final} мес. "
            "равно сумме — это полное присоединение (ч. 1 ст. 70 УК РФ).",
            None,
        )
    return None, None


def _general_part_finding(
    final: int, imprisonment: bool | None, maximum: int | None
) -> tuple[str | None, str | None]:
    """(violation, unknown) for ч. 2 ст. 70 — only a kind less severe than imprisonment."""
    if imprisonment is True:
        return None, None
    if imprisonment is None:
        return None, "Не установлено, назначено ли окончательное наказание в виде лишения свободы."
    if maximum is None:
        return None, (
            "Не установлен максимальный срок или размер этого вида наказания, предусмотренный "
            "Общей частью УК РФ."
        )
    if final > maximum:
        return (
            f"Окончательное наказание {final} превышает максимум {maximum}, предусмотренный "
            "для этого вида наказания Общей частью УК РФ (ч. 2 ст. 70 УК РФ).",
            None,
        )
    return None, None


def check_sentences_attachment(
    facts: SentencesCumulationFacts, draft: DraftSentenceAttachment
) -> CheckResult:
    _reject_negative(facts.new_sentence_months, facts.unserved_months, draft.final_term)
    if draft.general_part_maximum is not None and draft.general_part_maximum <= 0:
        raise ValueError("Максимум вида наказания должен быть положительным.")
    if draft.by_cumulation is False:
        return _attachment_result(
            CheckStatus.OK, "Наказание по совокупности приговоров не назначается."
        )
    if draft.by_cumulation is None:
        return _attachment_result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначается ли наказание по совокупности приговоров.",
        )
    if draft.life_imprisonment:
        return _attachment_result(
            CheckStatus.INSUFFICIENT_DATA,
            "Назначено пожизненное лишение свободы: присоединение по ч. 1 ст. 70 УК РФ "
            "в сроках не вычисляется.",
        )
    final = draft.final_term
    if final is None:
        return _attachment_result(
            CheckStatus.INSUFFICIENT_DATA,
            "В проекте не установлен срок окончательного наказания.",
        )
    findings = [
        _sum_finding(final, facts, draft.method),
        _general_part_finding(final, draft.imprisonment, draft.general_part_maximum),
    ]
    violations = [violation for violation, _ in findings if violation]
    if violations:
        return _attachment_result(CheckStatus.POSSIBLE_VIOLATION, " ".join(violations))
    unknown = [gap for _, gap in findings if gap]
    if unknown:
        return _attachment_result(CheckStatus.INSUFFICIENT_DATA, " ".join(unknown))
    return _attachment_result(
        CheckStatus.OK, "Окончательное наказание соответствует ч. 1 и ч. 2 ст. 70 УК РФ."
    )
