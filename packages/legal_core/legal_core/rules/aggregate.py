# Domain Layer — the final imprisonment term of several offences or several verdicts.
# ч. 2–3 ст. 69 УК РФ: by partial or full addition the term cannot exceed by more than one half
# the maximum term for the most serious of the offences; by absorption it equals the stricter
# one, so it is never below the longest term imposed for a count.
# ч. 4 ст. 70 УК РФ: the final term by several verdicts must exceed the term for the new offence.
# ч. 2 ст. 56 УК РФ: no more than 25 years by ч. 3–5 ст. 69 and no more than 30 years by ст. 70.
# Not checked: the unserved part of the earlier verdict (not read from the operative part),
# ч. 4–5 ст. 69, life imprisonment, other kinds of punishment.

from fractions import Fraction

from legal_core.checks import CheckResult, CheckStatus

NEEDS_LEGAL_REVIEW = True
SOURCE = (
    "УК РФ ст. 56, 69, 70, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/ "
    "(УК РФ ред. от 04.08.2026)"
)
_ART69_TOTAL_CAP = 25 * 12
_ART70_TOTAL_CAP = 30 * 12


def _months(value: float) -> str:
    if value != int(value):
        return f"{float(value):g} мес."
    years, months = divmod(int(value), 12)
    parts = ([f"{years} г."] if years else []) + ([f"{months} мес."] if months else [])
    return " ".join(parts) or "0 мес."


def check_final_term(
    *,
    rule: str | None,
    final_months: int | None,
    count_months: list[int | None],
    count_max_months: list[float | None],
) -> CheckResult:
    """Candidate check of the final imprisonment term.

    rule is "69.2", "69.3" or "70"; count_max_months are the maxima that bind the court for
    each count (already reduced under ст. 66 for an unfinished offence).
    """
    norm = {
        "69.2": "Окончательное наказание: ч. 2 ст. 69 УК РФ",
        "69.3": "Окончательное наказание: ч. 3 ст. 69 УК РФ",
        "70": "Окончательное наказание: ст. 70 УК РФ",
    }.get(rule or "", "Окончательное наказание: ст. 69, 70 УК РФ")

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(norm, status, why, SOURCE, NEEDS_LEGAL_REVIEW)

    if rule not in ("69.2", "69.3", "70"):
        return result(CheckStatus.INSUFFICIENT_DATA, "Правило сложения наказаний не распознано.")
    terms = [m for m in count_months if m is not None]
    if final_months is None or not terms or len(terms) != len(count_months):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Сроки лишения свободы по эпизодам или итоговый срок не прочитаны.",
        )
    longest = max(terms)
    if rule == "70":
        if final_months <= longest:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                f"Итог {_months(final_months)} не больше срока за новое преступление "
                f"{_months(longest)} (ч. 4 ст. 70 УК РФ).",
            )
        if final_months > _ART70_TOTAL_CAP:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                f"Итог {_months(final_months)} больше 30 лет (ч. 2 ст. 56 УК РФ).",
            )
        return result(
            CheckStatus.OK,
            f"Итог {_months(final_months)} больше срока за новое преступление и не больше 30 лет. "
            "Неотбытая часть прежнего приговора не проверена.",
        )
    if final_months < longest:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Итог {_months(final_months)} меньше самого строгого срока по эпизоду "
            f"{_months(longest)}.",
        )
    maxima = [m for m in count_max_months if m is not None]
    if len(maxima) != len(count_max_months):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            f"Итог {_months(final_months)} не меньше срока по эпизодам; верхний предел не "
            "проверен — санкция одного из эпизодов не найдена.",
        )
    cap = Fraction(max(maxima)).limit_denominator() * Fraction(3, 2)
    if rule == "69.3":
        cap = min(cap, Fraction(_ART69_TOTAL_CAP))
    if final_months > cap:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Итог {_months(final_months)} больше предела {_months(cap)}: максимум за наиболее "
            "тяжкое преступление, увеличенный наполовину.",
        )
    if final_months > sum(terms) or (rule == "69.3" and final_months <= longest):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Итог не соответствует частичному/полному сложению: "
            "больше суммы либо не больше самого строгого эпизода по ч. 3.",
        )
    return result(
        CheckStatus.OK,
        f"Итог {_months(final_months)}: не меньше срока по эпизодам и не больше предела "
        f"{_months(cap)}.",
    )
