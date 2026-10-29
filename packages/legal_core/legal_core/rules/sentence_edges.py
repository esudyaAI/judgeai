"""Candidate edge checks, УК РФ red.04.08.2026, verified 29.10.2026.

Sources: articles 66,69,70,71,72 at consultant.ru/document/cons_doc_LAW_10699/.
Exact unit conversion follows ч.1 ст.71 and ч.2 ст.72 (240h = 1 month).
Unsupported independent punishments and missing chronology remain insufficient_data.
All results require legal review, including law edition on the offence date.
"""

from fractions import Fraction

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import (
    Category,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
    StatutorySanction,
    Unfinished,
)

SOURCE = "https://www.consultant.ru/document/cons_doc_LAW_10699/"


def imprisonment_equivalent(term: PunishmentTerm | None) -> Fraction | None:
    if term is None or term.amount is None:
        return None
    ratios = {
        PunishmentKind.IMPRISONMENT: 1,
        PunishmentKind.FORCED_LABOUR: 1,
        PunishmentKind.ARREST: 1,
        PunishmentKind.DISCIPLINARY_MILITARY_UNIT: 1,
        PunishmentKind.RESTRICTION_OF_FREEDOM: 2,
        PunishmentKind.CORRECTIONAL_WORKS: 3,
        PunishmentKind.MILITARY_SERVICE_RESTRICTION: 3,
    }
    value = Fraction(str(term.amount))
    if term.kind is PunishmentKind.COMPULSORY_WORKS and term.unit is MeasureUnit.HOURS:
        return value / 240
    ratio = ratios.get(term.kind)
    if ratio and term.unit in (MeasureUnit.MONTHS, MeasureUnit.DAYS):
        return value / ratio / (30 if term.unit is MeasureUnit.DAYS else 1)
    return None


def check_article70(
    final: PunishmentTerm,
    new: PunishmentTerm | None,
    unserved: PunishmentTerm | None,
    joined: PunishmentTerm | None,
) -> CheckResult:
    norm = "Окончательное наказание: ст. 70, 71 УК РФ"

    def result(status, text):
        return CheckResult(norm, status, text, SOURCE, True)

    end, current = imprisonment_equivalent(final), imprisonment_equivalent(new)
    balance, added = imprisonment_equivalent(unserved), imprisonment_equivalent(joined)
    if end is None or current is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Виды наказания исполняются самостоятельно или сроки не "
            "прочитаны; автоматическое сложение не выполнено.",
        )
    if end <= current:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог не больше наказания за новое преступление (ч. 4 ст. 70).",
        )
    if final.kind is PunishmentKind.IMPRISONMENT and end > 360:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог превышает общий предел 30 лет; специальные "
            "исключения ст. 56 требуют отдельной проверки.",
        )
    if balance is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не определена вся неотбытая часть прежнего приговора; "
            "присоединённая часть её не заменяет.",
        )
    if end <= balance:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог не больше неотбытой части прежнего приговора (ч. 4 ст. 70).",
        )
    if end > current + balance:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог превышает сумму нового наказания и всей неотбытой части.",
        )
    if joined is not None:
        if added is None:
            return result(
                CheckStatus.INSUFFICIENT_DATA, "Присоединённая часть не сопоставлена по ст. 71."
            )
        if added > balance or end != current + added:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                "Присоединено больше неотбытой части либо итог не равен "
                "новому наказанию с присоединённой частью.",
            )
    return result(
        CheckStatus.OK,
        "Проверены оба строгих нижних предела ч. 4 ст. 70 и "
        "сумма присоединения с пересчётом по ст. 71/72; редакция и основания требуют сверки.",
    )


def check_article69_part(
    part: int | None,
    categories: list[Category | None],
    stages: list[Unfinished | None],
    *,
    absorption: bool = False,
) -> CheckResult:
    norm = "Часть ст. 69 УК РФ"

    def result(status, text):
        return CheckResult(norm, status, text, SOURCE, True)

    if part in (4, 5):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Ч. 4 требует отдельного сложения дополнительных "
            "наказаний; ч. 5 — дат преступлений, прежнего приговора "
            "и зачёта отбытого. Эти факты не заменяются общей ссылкой.",
        )
    if (
        part not in (2, 3)
        or not categories
        or len(categories) != len(stages)
        or any(c is None for c in categories)
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Не определены часть ст. 69 или категории всех эпизодов."
        )
    requires_addition = any(
        c in (Category.GRAVE, Category.ESPECIALLY_GRAVE) and stage is None
        for c, stage in zip(categories, stages, strict=True)
    )
    expected = 3 if requires_addition else 2
    if part != expected or (expected == 3 and absorption):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Для этого набора эпизодов применима ч. {expected} ст. 69; "
            "поглощение по ч. 3 не допускается.",
        )
    return result(
        CheckStatus.OK,
        f"Выбор ч. {expected} соответствует категориям и стадиям всех эпизодов; "
        "порядок и полнота сложения проверяются отдельно.",
    )


def check_additional(term: PunishmentTerm, sanctions: list[StatutorySanction]) -> CheckResult:
    norm = "Дополнительное наказание: пределы санкции"

    def result(status, text):
        return CheckResult(norm, status, text, SOURCE, True)

    alternatives = [
        s for s in sanctions if s.kind is term.kind and s.role is SanctionRole.ADDITIONAL
    ]
    if not alternatives:
        if term.kind is PunishmentKind.DEPRIVATION_OF_RIGHT:
            return result(
                CheckStatus.INSUFFICIENT_DATA,
                "Лишение права вне санкции возможно по ч. 3 ст. 47; "
                "необходима проверка основания и мотивировки.",
            )
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Дополнительный вид наказания не предусмотрен прочитанной санкцией.",
        )
    matching = [s for s in alternatives if s.unit is term.unit and term.amount is not None]
    if not matching:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не определён сопоставимый размер дополнительного наказания.",
        )
    if any(
        (s.min_value is None or term.amount >= s.min_value)
        and (s.max_value is None or term.amount <= s.max_value)
        for s in matching
    ):
        if any(s.max_value is None for s in matching):
            return result(
                CheckStatus.INSUFFICIENT_DATA,
                "Верхний предел дополнительного наказания не прочитан.",
            )
        return result(
            CheckStatus.OK,
            "Вид и размер дополнительного наказания соответствуют прочитанной санкции.",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION, "Размер дополнительного наказания вне пределов санкции."
    )


def check_other_aggregate(
    final: PunishmentTerm,
    counts: list[PunishmentTerm],
    maxima: list[float | None],
    rule: str | None,
) -> CheckResult:
    """Homogeneous non-custodial ч.2 ст.69. Mixed independent penalties are not collapsed."""
    norm = "Совокупность: ст. 69 УК РФ"

    def result(status, why):
        return CheckResult(norm, status, why, SOURCE, True)

    if (
        rule != "69.2"
        or not counts
        or any(t.kind is not final.kind or t.unit is not final.unit for t in counts)
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Разные виды или неподдержанная часть: требуется "
            "отдельное исполнение/пересчёт, общий размер не угадан.",
        )
    if (
        final.amount is None
        or any(t.amount is None for t in counts)
        or len(maxima) != len(counts)
        or any(m is None for m in maxima)
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Не прочитаны все размеры и максимумы санкций."
        )
    amount = Fraction(str(final.amount))
    terms = [Fraction(str(t.amount)) for t in counts]
    cap = Fraction(str(max(maxima))) * Fraction(3, 2)
    if amount < max(terms) or amount > sum(terms) or amount > cap:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог вне интервала поглощения/сложения либо выше полутора максимумов санкции.",
        )
    general = {
        PunishmentKind.COMPULSORY_WORKS: 480,
        PunishmentKind.CORRECTIONAL_WORKS: 24,
        PunishmentKind.FORCED_LABOUR: 60,
        PunishmentKind.RESTRICTION_OF_FREEDOM: 48,
    }.get(final.kind)
    if general is not None and amount > general:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог выше общего предела вида наказания (ст.49/50/53/53.1).",
        )
    return result(
        CheckStatus.OK,
        "Проверены сумма, поглощение и полтора максимума "
        "санкции одного вида; общий предел вида и редакцию закона необходимо сверить.",
    )


def check_additional_aggregate(
    final: PunishmentTerm, counts: list[PunishmentTerm], statutory_maximum: float | None = None
) -> CheckResult:
    """ч.4 ст.69 and ст.47/53, reviewed source edition 04.08.2026; judicial review required."""
    norm = "Совокупность дополнительных наказаний: ч. 4 ст. 69 УК РФ"

    def result(status, why):
        return CheckResult(norm, status, why, SOURCE, True)

    same = [t for t in counts if t.kind is final.kind and t.unit is final.unit]
    if final.amount is None or not same or any(t.amount is None for t in same):
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Дополнительные наказания всех эпизодов не сопоставлены."
        )
    cap = 24 if final.kind is PunishmentKind.RESTRICTION_OF_FREEDOM else None
    if final.kind is PunishmentKind.DEPRIVATION_OF_RIGHT:
        cap = max(36, statutory_maximum or 0)
    if cap is None or final.unit is not MeasureUnit.MONTHS:
        return result(
            CheckStatus.INSUFFICIENT_DATA, "Общий предел этого дополнительного вида не определён."
        )
    if (
        final.amount > cap
        or final.amount > sum(t.amount for t in same)
        or final.amount < max(t.amount for t in same)
    ):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итоговое дополнительное наказание вне суммы/поглощения или общего предела вида.",
        )
    return result(
        CheckStatus.OK, "Проверены сложение дополнительных наказаний и общий предел вида."
    )


def check_prior_chronology(
    offence_dates, prior_date, credited: PunishmentTerm | None
) -> CheckResult:
    """Eligibility of ч.5 ст.69 from explicit dates; same-day order is not guessed."""
    norm = "Хронология и зачёт: ч. 5 ст. 69 УК РФ"

    def result(status, why):
        return CheckResult(norm, status, why, SOURCE, True)

    if not offence_dates or any(d is None for d in offence_dates) or prior_date is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не определены даты всех преступлений и прежнего приговора для ч. 5 ст. 69.",
        )
    if any(d > prior_date for d in offence_dates):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Есть преступление после прежнего приговора; применение "
            "к нему ч. 5 ст. 69 требует проверки по ст. 70.",
        )
    if any(d == prior_date for d in offence_dates):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Преступление и прежний приговор в один день: порядок "
            "событий по одной дате не установлен.",
        )
    if credited is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Все преступления раньше прежнего приговора, но зачёт "
            "отбытого по первому приговору не прочитан.",
        )
    return result(
        CheckStatus.OK,
        "Даты соответствуют ч. 5 ст. 69; размер зачёта "
        "прочитан. Полнота прежних эпизодов и арифметика итогового наказания проверяются отдельно.",
    )
