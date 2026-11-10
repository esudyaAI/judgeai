# Domain Layer — ч. 2 и 2.1 ст. 58 УК РФ «Назначение осужденным к лишению свободы вида
# исправительного учреждения» (часть срока в тюрьме): ч. 2 — ред. ФЗ от 08.12.2003 N 162-ФЗ и
# от 27.12.2018 N 569-ФЗ; ч. 2.1 — введена ФЗ N 569-ФЗ, ред. ФЗ от 28.04.2023 N 157-ФЗ.
# Разъяснения — Пленум ВС РФ от 29.05.2014 N 9 (ред. от 26.11.2024 N 36): п. 5 (мотивы и срок в
# резолютивной части), п. 6 (совокупность).
# Ч. 2: основанием служит особо тяжкое преступление со сроком свыше пяти лет, статья из перечня
# ч. 2 или особо опасный рецидив; условие «свыше пяти лет» текст связывает только с особо тяжким
# преступлением. Назначение — право суда, поэтому отсутствие тюрьмы при основании ч. 2 не ошибка.
# Ч. 2.1: для статей перечня часть срока в тюрьме назначается обязательно, не менее года после
# зачёта содержания под стражей. Перечни статей обеих частей — данные (редакция зависит от даты
# деяния), поэтому принадлежность к ним сообщает вызывающий, как и срок за каждое особо тяжкое
# преступление (ППВС № 9 п. 6 — срок за само это преступление, а не итог совокупности).
# Неизвестный значимый факт → «недостаточно данных». Толкование сверяется в T23.
# TODO(T4/T23): ППВС № 9 п. 7 (новое преступление во время отбывания в тюрьме) не смоделирован.
from dataclasses import dataclass

from legal_core.checks import CheckResult, CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import Sex

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art58.prison_part"
NORM = "Часть срока в тюрьме: ч. 2 и 2.1 ст. 58 УК РФ"
SOURCE = (
    "УК РФ ст. 58, ч. 2 (ред. ФЗ от 27.12.2018 N 569-ФЗ), ч. 2.1 (ред. ФЗ от 28.04.2023 "
    "N 157-ФЗ) — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891"
    "&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735"
    "b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23); Пленум ВС РФ от "
    "29.05.2014 N 9 (ред. от 26.11.2024 N 36), пп. 5–6"
)

_FIVE_YEARS_MONTHS = 60
_MANDATORY_MINIMUM_MONTHS = 12


@dataclass(frozen=True)
class PrisonPartFacts:
    """Established facts of the case; None means the fact is not extracted.

    especially_grave_terms_months — imprisonment imposed for each especially grave offence
    (empty — no such offence); article_in_part2_list / article_in_part21_list — the
    conviction falls under the article lists of ч. 2 / ч. 2.1 in the applicable edition.
    """

    conditional: bool | None
    life_imprisonment: bool
    sex: Sex | None
    minor_at_sentencing: bool | None
    recidivism: Recidivism
    especially_grave_terms_months: tuple[int, ...] | None
    article_in_part2_list: bool | None
    article_in_part21_list: bool | None


@dataclass(frozen=True)
class DraftPrisonPart:
    """What the draft says about a prison part; None means not extracted.

    months — the prison term as stated; credited_detention_months — pre-trial detention
    credited against it; motivated — the draft gives reasons (ППВС № 9 п. 5).
    """

    assigned: bool | None
    months: int | None = None
    credited_detention_months: int | None = None
    motivated: bool | None = None


def _result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)


def _insufficient(why: str) -> CheckResult:
    return _result(CheckStatus.INSUFFICIENT_DATA, why)


def _flag(why: str) -> CheckResult:
    return _result(CheckStatus.POSSIBLE_VIOLATION, why)


_UNKNOWN_PERSON = "Не установлены пол осуждённого или его возраст к моменту приговора."
_UNKNOWN_PART21 = "Не установлено, относится ли осуждение к статьям ч. 2.1 ст. 58 УК РФ."


def _excluded(facts: PrisonPartFacts) -> bool:
    """Ч. 2 и 2.1 обращены к мужчинам; несовершеннолетним назначается воспитательная колония."""
    return facts.sex is Sex.FEMALE or facts.minor_at_sentencing is True


def _person_unknown(facts: PrisonPartFacts) -> bool:
    return facts.sex is None or facts.minor_at_sentencing is None


def _check_not_assigned(facts: PrisonPartFacts) -> CheckResult:
    if facts.article_in_part21_list is False or _excluded(facts):
        return _result(
            CheckStatus.OK, "Часть срока в тюрьме не назначена, обязательных оснований нет."
        )
    if _person_unknown(facts):
        return _insufficient(_UNKNOWN_PERSON)
    if facts.article_in_part21_list is None:
        return _insufficient(_UNKNOWN_PART21)
    return _flag(
        "Осуждение по статье из перечня ч. 2.1 ст. 58 УК РФ: отбывание части срока в тюрьме "
        "назначается обязательно, в проекте оно не найдено."
    )


def _check_part21_term(draft: DraftPrisonPart) -> CheckResult:
    below = (
        "Период в тюрьме после зачёта содержания под стражей должен быть не менее одного года "
        "(ч. 2.1 ст. 58 УК РФ)."
    )
    if draft.months is None:
        return _insufficient("В проекте не установлен срок отбывания в тюрьме.")
    if draft.months < _MANDATORY_MINIMUM_MONTHS:
        return _flag(below)
    if draft.credited_detention_months is None:
        return _insufficient("Не установлено время содержания под стражей, подлежащее зачёту.")
    if draft.months - draft.credited_detention_months < _MANDATORY_MINIMUM_MONTHS:
        return _flag(below)
    return _result(CheckStatus.OK, "Часть срока в тюрьме соответствует ч. 2.1 ст. 58 УК РФ.")


def _part2_ground(facts: PrisonPartFacts) -> bool | None:
    terms = facts.especially_grave_terms_months
    if (
        (terms is not None and any(term > _FIVE_YEARS_MONTHS for term in terms))
        or facts.recidivism is Recidivism.ESPECIALLY_DANGEROUS
        or facts.article_in_part2_list is True
    ):
        return True
    if terms is None or facts.recidivism is Recidivism.UNKNOWN:
        return None
    return None if facts.article_in_part2_list is None else False


def _check_assigned(facts: PrisonPartFacts, draft: DraftPrisonPart) -> CheckResult:
    if _excluded(facts):
        return _flag(
            "Часть срока в тюрьме назначена женщине или несовершеннолетнему: ч. 2 и 2.1 ст. 58 "
            "УК РФ такого не предусматривают."
        )
    if _person_unknown(facts):
        return _insufficient(_UNKNOWN_PERSON)
    if facts.article_in_part21_list is None:
        return _insufficient(_UNKNOWN_PART21)
    if facts.article_in_part21_list:
        return _check_part21_term(draft)
    ground = _part2_ground(facts)
    if ground is None:
        return _insufficient("Не установлены сведения об основаниях ч. 2 ст. 58 УК РФ.")
    if not ground:
        return _flag("Часть срока в тюрьме назначена при отсутствии оснований ч. 2 ст. 58 УК РФ.")
    if draft.months is None:
        return _insufficient("В проекте не установлен срок отбывания в тюрьме (ППВС № 9 п. 5).")
    if draft.motivated is None:
        return _insufficient("Не установлено, приведены ли мотивы назначения тюрьмы.")
    if not draft.motivated:
        return _flag("Назначение части срока в тюрьме не мотивировано (ППВС № 9 п. 5).")
    return _result(CheckStatus.OK, "Часть срока в тюрьме назначена по основанию ч. 2 ст. 58 УК РФ.")


def check_prison_part(facts: PrisonPartFacts, draft: DraftPrisonPart) -> CheckResult:
    """Candidate check of a prison part (ч. 2, 2.1 ст. 58) for real imprisonment in the draft."""
    if facts.conditional is None:
        return _insufficient("Не установлено, назначено ли наказание условно (ст. 73 УК РФ).")
    if draft.assigned is None:
        return _insufficient("Не установлено, назначена ли в проекте часть срока в тюрьме.")
    if facts.conditional:
        if draft.assigned:
            return _flag("При условном осуждении часть срока в тюрьме не назначается.")
        return _result(CheckStatus.OK, "Наказание условно, часть срока в тюрьме не назначена.")
    if facts.life_imprisonment:
        return _insufficient("При пожизненном лишении свободы эта проверка не выполняется.")
    return _check_assigned(facts, draft) if draft.assigned else _check_not_assigned(facts)


# --- п. 7 ППВС № 9: новое преступление во время отбывания наказания в тюрьме ----------------
# Наказание назначается по совокупности приговоров (ст. 70 УК РФ); в приговоре указывается, какая
# его часть отбывается в тюрьме, и этот срок не может быть менее неотбытой части наказания в
# тюрьме по предыдущему приговору; вид учреждения для оставшейся части определяется по ст. 58 УК РФ
# и указывается в резолютивной части. Пункт обращён к лицам мужского пола — женщины в тюрьме
# наказание не отбывают, поэтому пол здесь отдельно не проверяется. Неотбытую часть передаёт
# вызывающий (она — факт предыдущего приговора, а не вычисление ядра).

NEW_OFFENCE_RULE_KEY = "art58.prison_new_offence"
NEW_OFFENCE_NORM = (
    "Новое преступление во время отбывания наказания в тюрьме: ч. 2 ст. 58 УК РФ, п. 7 ППВС № 9"
)
NEW_OFFENCE_SOURCE = (
    "Пленум ВС РФ от 29.05.2014 N 9 (ред. от 26.11.2024 N 36), п. 7 — "
    "https://www.consultant.ru/document/cons_doc_LAW_163742/, сверено 10.11.2026 по коротким "
    "цитатам (статус unreviewed); УК РФ ст. 58, ст. 70 — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, sha256 "
    "0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (статус unreviewed)"
)


def _non_negative(value: int | None, name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class PrisonNewOffenceFacts:
    """Facts of the earlier sentence; None means the fact is not extracted.

    offence_while_in_prison — the new offence was committed while serving the prison part of an
    earlier sentence; unserved_prison_months — the unserved prison part of that sentence.
    """

    offence_while_in_prison: bool | None
    unserved_prison_months: int | None
    life_imprisonment: bool

    def __post_init__(self) -> None:
        _non_negative(self.unserved_prison_months, "unserved_prison_months")


@dataclass(frozen=True)
class DraftCumulativePrison:
    """What the draft says; None means not extracted.

    cumulative_sentences — the punishment is imposed by aggregation of sentences (ст. 70);
    prison_months — the part to be served in prison (0 — none is stated);
    remaining_regime_stated — the operative part names the institution for the remaining term.
    """

    cumulative_sentences: bool | None
    prison_months: int | None
    remaining_regime_stated: bool | None

    def __post_init__(self) -> None:
        _non_negative(self.prison_months, "prison_months")


def _new_offence_result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(
        NEW_OFFENCE_NORM, status, why, NEW_OFFENCE_SOURCE, NEEDS_LEGAL_REVIEW, NEW_OFFENCE_RULE_KEY
    )


def _prison_term_finding(facts: PrisonNewOffenceFacts, draft: DraftCumulativePrison) -> bool | None:
    """True — срок в тюрьме не меньше неотбытой части; False — меньше; None — не установлено."""
    if draft.prison_months is None or facts.unserved_prison_months is None:
        return None
    return draft.prison_months >= facts.unserved_prison_months


def check_new_offence_in_prison(
    facts: PrisonNewOffenceFacts, draft: DraftCumulativePrison
) -> CheckResult:
    """Candidate check of п. 7 ППВС № 9 for a new offence committed while serving in prison.

    A known violation is reported even if other facts are missing; otherwise any missing fact
    gives «недостаточно данных».
    """
    if facts.offence_while_in_prison is None:
        return _new_offence_result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, совершено ли преступление во время отбывания наказания в тюрьме.",
        )
    if not facts.offence_while_in_prison:
        return _new_offence_result(
            CheckStatus.OK,
            "Преступление совершено не во время отбывания наказания в тюрьме — п. 7 ППВС № 9 "
            "не применяется.",
        )
    if facts.life_imprisonment:
        return _new_offence_result(
            CheckStatus.INSUFFICIENT_DATA,
            "При пожизненном лишении свободы эта проверка не выполняется.",
        )
    findings = (
        (
            draft.cumulative_sentences,
            "Преступление совершено во время отбывания наказания в тюрьме: наказание назначается "
            "по совокупности приговоров (ст. 70 УК РФ, п. 7 ППВС № 9), в проекте этого нет.",
            "Не установлено, назначено ли наказание по совокупности приговоров.",
        ),
        (
            _prison_term_finding(facts, draft),
            "Срок отбывания в тюрьме не может быть менее неотбытой части наказания в тюрьме по "
            "предыдущему приговору (п. 7 ППВС № 9).",
            "Не установлены срок отбывания в тюрьме по проекту или неотбытая часть наказания в "
            "тюрьме по предыдущему приговору.",
        ),
        (
            draft.remaining_regime_stated,
            "В резолютивной части не указан вид исправительного учреждения для оставшейся части "
            "наказания (ст. 58 УК РФ, п. 7 ППВС № 9).",
            "Не установлено, указан ли вид исправительного учреждения для оставшейся части "
            "наказания.",
        ),
    )
    for finding, violation, _ in findings:
        if finding is False:
            return _new_offence_result(CheckStatus.POSSIBLE_VIOLATION, violation)
    for finding, _, missing in findings:
        if finding is None:
            return _new_offence_result(CheckStatus.INSUFFICIENT_DATA, missing)
    return _new_offence_result(
        CheckStatus.OK,
        "Наказание назначено по совокупности приговоров, срок в тюрьме не меньше неотбытой "
        "части, вид учреждения для оставшейся части указан.",
    )
