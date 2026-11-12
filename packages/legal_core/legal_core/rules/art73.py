# Domain Layer — п. «в» ч. 1 ст. 73 УК РФ «Условное осуждение».
# ч. 1: «... Условное осуждение не назначается: ... в) при опасном или особо опасном рецидиве.»
# (часть в ред. ФЗ от 16.10.2012 N 172-ФЗ). The bar is absolute: no circumstance of the case
# lifts it. Пленум ВС РФ № 58 от 22.12.2015, п. 62: for several offences the conditional
# decision is taken once, for the final punishment, so the caller passes the final decision.
# The kind of recidivism comes from art18 (the caller classifies it on the offence date).
# п. «б»: a grave or especially grave offence during probation or the unserved part after parole,
# the earlier punishment being for an intentional offence; the caller passes the periods.
# General limits of ч. 1 (T4.12): only correctional works, restriction in military service,
# a disciplinary military unit or imprisonment up to eight years may be conditional; the caller
# passes the final punishment (Пленум № 58, п. 62). «До восьми лет» is read as inclusive —
# eight years may be conditional; the reading is for legal review (T23).
# пп. «а», «а1» (T4.13): a conditional sentence is barred for offences against the sexual
# inviolability of minors under fourteen (п. «а») and for the offences listed in п. «а1». The
# list of п. «а1» changes with editions (last — ФЗ от 17.11.2025 N 420-ФЗ), so it is data: the
# caller says whether each offence falls under it in the applicable edition; no article
# numbers are hard-coded here.

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category, PunishmentKind
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art73.conditional_ban"
NORM = "Запрет условного осуждения при опасном и особо опасном рецидиве: п. «в» ч. 1 ст. 73 УК РФ"
SOURCE = (
    "УК РФ ст. 73 ч. 1 (ред. ФЗ от 16.10.2012 N 172-ФЗ) — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, "
    "sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (карточка: "
    "изменение от 04.08.2026 N 300-ФЗ; статус unreviewed, периоды действия сверить в T23); "
    "Пленум ВС РФ от 22.12.2015 N 58 (ред. от 23.12.2025), п. 62 — официальный файл vsrf.ru, "
    "sha256 3e244ff596b2a779fc32d5f61aa6567680f7a52540b9ab3c7f0be73753b77c7b"
)

SUPERVISION_RULE_KEY = "art73.offence_during_supervision"
SUPERVISION_NORM = (
    "Запрет условного осуждения за тяжкое или особо тяжкое преступление в испытательный срок "
    "или при условно-досрочном освобождении: п. «б» ч. 1 ст. 73 УК РФ"
)
SUPERVISION_SOURCE = (
    "УК РФ ст. 73 ч. 1 п. «б» (ч. 1 в ред. ФЗ от 16.10.2012 N 172-ФЗ) — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, "
    "sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (статус "
    "unreviewed, периоды действия сверить в T23)"
)

_BARRED = {
    Recidivism.DANGEROUS: "опасный",
    Recidivism.ESPECIALLY_DANGEROUS: "особо опасный",
}
_NOT_CHECKED = (
    "Пункты «а», «а1», «б» ч. 1 ст. 73 УК РФ и пределы ч. 1 (вид наказания, лишение свободы "
    "до восьми лет) этой проверкой не оценивались."
)

LIMITS_RULE_KEY = "art73.conditional_limits"
LIMITS_NORM = (
    "Виды наказания и предел лишения свободы, которые могут быть назначены условно: "
    "ч. 1 ст. 73 УК РФ"
)
LIMITS_SOURCE = (
    "УК РФ ст. 73 ч. 1, абзац первый (ч. 1 в ред. ФЗ от 16.10.2012 N 172-ФЗ) — официальная "
    "выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена "
    "27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b "
    "(статус unreviewed, периоды действия сверить в T23)"
)
MAX_CONDITIONAL_IMPRISONMENT_MONTHS = 96  # «лишение свободы на срок до восьми лет»

_CONDITIONAL_KINDS = frozenset(
    {
        PunishmentKind.CORRECTIONAL_WORKS,
        PunishmentKind.MILITARY_SERVICE_RESTRICTION,
        PunishmentKind.DISCIPLINARY_MILITARY_UNIT,
        PunishmentKind.IMPRISONMENT,
    }
)
_ALLOWED_TEXT = (
    "исправительные работы, ограничение по военной службе, содержание в дисциплинарной "
    "воинской части или лишение свободы на срок до восьми лет"
)


def check_conditional_sentence_recidivism_bar(
    *,
    recidivism: Recidivism,
    conditional_in_draft: bool | None,
) -> CheckResult:
    """Candidate check: a conditional sentence is not imposed with dangerous recidivism.

    ``recidivism`` — the kind classified by ст. 18 (``art18.classify_recidivism``).
    ``conditional_in_draft`` — whether the draft makes the final punishment conditional
    (ст. 73), ``None`` — the draft position was not extracted.
    """

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)

    if conditional_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначено ли в проекте наказание условно (ст. 73 УК РФ).",
        )
    if not conditional_in_draft:
        return result(
            CheckStatus.OK,
            "Условное осуждение не назначено — п. «в» ч. 1 ст. 73 УК РФ не затрагивается.",
        )
    if recidivism is Recidivism.UNKNOWN:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Вид рецидива не установлен — запрет п. «в» ч. 1 ст. 73 УК РФ не проверен.",
        )
    if recidivism in _BARRED:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначено условное осуждение, но в действиях осуждённого {_BARRED[recidivism]} "
            "рецидив (ст. 18 УК РФ): условное осуждение при опасном или особо опасном "
            "рецидиве не назначается (п. «в» ч. 1 ст. 73 УК РФ).",
        )
    found = "рецидива нет" if recidivism is Recidivism.NONE else "рецидив простой"
    return result(
        CheckStatus.OK,
        f"Условное осуждение назначено; {found} — запрет п. «в» ч. 1 ст. 73 УК РФ не "
        f"применяется. {_NOT_CHECKED}",
    )


def check_conditional_sentence_limits(
    *,
    final_kind: PunishmentKind | None,
    final_months: int | None,
    conditional_in_draft: bool | None,
) -> CheckResult:
    """Candidate check of the general limits of ч. 1 ст. 73 for the final punishment.

    ``final_kind`` — the kind of the final main punishment, ``final_months`` — its term in
    months (needed for imprisonment only); ``None`` — the fact was not extracted.
    """
    if final_months is not None and final_months < 0:
        raise ValueError("a punishment term must not be negative")

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            LIMITS_NORM, status, why, LIMITS_SOURCE, NEEDS_LEGAL_REVIEW, LIMITS_RULE_KEY
        )

    if conditional_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначено ли в проекте наказание условно (ст. 73 УК РФ).",
        )
    if not conditional_in_draft:
        return result(
            CheckStatus.OK,
            "Условное осуждение не назначено — пределы ч. 1 ст. 73 УК РФ не затрагиваются.",
        )
    if final_kind is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлен вид итогового наказания — пределы ч. 1 ст. 73 УК РФ не проверены.",
        )
    if final_kind not in _CONDITIONAL_KINDS:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Условным назначено наказание, которое ч. 1 ст. 73 УК РФ условным не допускает: "
            f"условно могут быть назначены только {_ALLOWED_TEXT}.",
        )
    if final_kind is not PunishmentKind.IMPRISONMENT:
        return result(
            CheckStatus.OK,
            "Вид наказания допускает условное осуждение (ч. 1 ст. 73 УК РФ).",
        )
    if final_months is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлен срок лишения свободы — предел ч. 1 ст. 73 УК РФ (до восьми лет) "
            "не проверен.",
        )
    if final_months > MAX_CONDITIONAL_IMPRISONMENT_MONTHS:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Условно назначено лишение свободы на {final_months} мес., тогда как условное "
            "осуждение допускается при лишении свободы на срок до восьми лет "
            "(ч. 1 ст. 73 УК РФ).",
        )
    return result(
        CheckStatus.OK,
        f"Лишение свободы на {final_months} мес. не превышает восьми лет — условное осуждение "
        "в пределах ч. 1 ст. 73 УК РФ.",
    )


class SupervisionKind(StrEnum):
    """The prior regime during which a new offence bars a conditional sentence (п. «б»)."""

    PROBATION = "probation"  # испытательный срок при условном осуждении
    PAROLE = "parole"  # неотбытая часть наказания при условно-досрочном освобождении


@dataclass(frozen=True)
class PriorSupervision:
    """One prior period of supervision; ``None`` means the fact is unknown.

    ``intentional`` — whether the punishment was imposed for an intentional offence.
    """

    kind: SupervisionKind
    started_on: date | None
    ended_on: date | None
    intentional: bool | None

    def __post_init__(self) -> None:
        if self.started_on and self.ended_on and self.started_on > self.ended_on:
            raise ValueError("a supervision period must not end before it starts")


_SUPERVISION_LABEL = {
    SupervisionKind.PROBATION: "в течение испытательного срока при условном осуждении",
    SupervisionKind.PAROLE: (
        "в течение неотбытой части наказания при условно-досрочном освобождении"
    ),
}


def _bars_conditional(period: PriorSupervision, offence_date: date) -> bool | None:
    """Whether the offence falls in a period that bars it; None — cannot decide from the facts."""
    if (period.started_on and offence_date < period.started_on) or (
        period.ended_on and offence_date > period.ended_on
    ):
        return False
    if period.started_on is None or period.ended_on is None:
        return None
    if offence_date in (period.started_on, period.ended_on):  # boundary days are not decided here
        return None
    return period.intentional


def check_conditional_sentence_during_supervision(
    *,
    offence_category: Category | None,
    offence_date: date | None,
    supervisions: Sequence[PriorSupervision] | None,
    conditional_in_draft: bool | None,
) -> CheckResult:
    """Candidate check of п. «б» ч. 1 ст. 73 for the new offence.

    ``supervisions`` — every prior probation or parole; empty — there were none, ``None`` —
    unknown. A boundary day of a period is "insufficient data", as in art86.
    """

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            SUPERVISION_NORM,
            status,
            why,
            SUPERVISION_SOURCE,
            NEEDS_LEGAL_REVIEW,
            SUPERVISION_RULE_KEY,
        )

    if conditional_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначено ли в проекте наказание условно (ст. 73 УК РФ).",
        )
    if not conditional_in_draft:
        return result(
            CheckStatus.OK,
            "Условное осуждение не назначено — п. «б» ч. 1 ст. 73 УК РФ не затрагивается.",
        )
    if offence_category is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлена категория преступления — запрет п. «б» ч. 1 ст. 73 УК РФ не проверен.",
        )
    if offence_category <= Category.MEDIUM:
        return result(
            CheckStatus.OK,
            "Преступление не относится к тяжким или особо тяжким — п. «б» ч. 1 ст. 73 УК РФ "
            "не применяется.",
        )
    if supervisions is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, было ли условное осуждение или условно-досрочное освобождение "
            "на момент преступления (п. «б» ч. 1 ст. 73 УК РФ).",
        )
    if not supervisions:
        return result(
            CheckStatus.OK,
            "Преступление совершено не в период условного осуждения или условно-досрочного "
            "освобождения — п. «б» ч. 1 ст. 73 УК РФ не применяется.",
        )
    if offence_date is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлена дата преступления — запрет п. «б» ч. 1 ст. 73 УК РФ не проверен.",
        )
    decisions = [(period, _bars_conditional(period, offence_date)) for period in supervisions]
    for period, barred in decisions:
        if barred:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                "Назначено условное осуждение за тяжкое или особо тяжкое преступление, "
                f"совершённое {_SUPERVISION_LABEL[period.kind]} за умышленное преступление: "
                "условное осуждение в этом случае не назначается (п. «б» ч. 1 ст. 73 УК РФ).",
            )
    if any(barred is None for _, barred in decisions):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Даты периода условного осуждения или условно-досрочного освобождения, совпадение "
            "с днём преступления или форма вины по прежнему приговору не позволяют проверить "
            "п. «б» ч. 1 ст. 73 УК РФ.",
        )
    return result(
        CheckStatus.OK,
        "Преступление совершено вне периода, запрещающего условное осуждение, — п. «б» ч. 1 "
        "ст. 73 УК РФ не применяется.",
    )


OFFENCE_LIST_RULE_KEY = "art73.offence_list_bar"
OFFENCE_LIST_NORM = (
    "Запрет условного осуждения за преступления против половой неприкосновенности "
    "несовершеннолетних, не достигших четырнадцатилетнего возраста, и за преступления "
    "перечня п. «а1»: пп. «а», «а1» ч. 1 ст. 73 УК РФ"
)
OFFENCE_LIST_SOURCE = (
    "УК РФ ст. 73 ч. 1 пп. «а», «а1» (ч. 1 в ред. ФЗ от 16.10.2012 N 172-ФЗ; п. «а1» введён "
    "ФЗ от 05.05.2014 N 130-ФЗ, в ред. ФЗ от 06.07.2016 N 375-ФЗ, от 01.04.2019 N 46-ФЗ, "
    "от 17.11.2025 N 420-ФЗ) — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, "
    "sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (статус "
    "unreviewed, периоды действия редакций перечня сверить в T23); Пленум ВС РФ от 22.12.2015 "
    "N 58 (ред. от 23.12.2025), п. 62"
)


@dataclass(frozen=True)
class ListedOffence:
    """One offence of the conviction and its place in the lists of пп. «а», «а1».

    ``article`` — how the draft qualifies it (for the explanation);
    ``child_sexual_inviolability`` — an offence against the sexual inviolability of a minor
    under fourteen (п. «а»); ``in_a1_list`` — the offence is in the list of п. «а1» in the
    edition applicable on the offence date. ``None`` — not established.
    """

    article: str
    child_sexual_inviolability: bool | None
    in_a1_list: bool | None

    def __post_init__(self) -> None:
        if not self.article.strip():
            raise ValueError("an offence must name its article")


def check_conditional_sentence_offence_bar(
    *,
    offences: Sequence[ListedOffence] | None,
    conditional_in_draft: bool | None,
) -> CheckResult:
    """Candidate check of пп. «а», «а1» ч. 1 ст. 73 for every offence of the conviction.

    The conditional decision concerns the final punishment (Пленум № 58, п. 62), so one barred
    offence is enough; an established bar is reported even when other facts are unknown.
    ``offences`` — ``None`` or empty means the offences were not extracted.
    """

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            OFFENCE_LIST_NORM,
            status,
            why,
            OFFENCE_LIST_SOURCE,
            NEEDS_LEGAL_REVIEW,
            OFFENCE_LIST_RULE_KEY,
        )

    if conditional_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначено ли в проекте наказание условно (ст. 73 УК РФ).",
        )
    if not conditional_in_draft:
        return result(
            CheckStatus.OK,
            "Условное осуждение не назначено — пп. «а», «а1» ч. 1 ст. 73 УК РФ не затрагиваются.",
        )
    if not offences:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлены преступления, за которые назначено наказание, — запрет "
            "пп. «а», «а1» ч. 1 ст. 73 УК РФ не проверен.",
        )
    reasons = []
    child = [o.article for o in offences if o.child_sexual_inviolability]
    if child:
        reasons.append(
            f"преступление против половой неприкосновенности несовершеннолетнего, не достигшего "
            f"четырнадцатилетнего возраста ({'; '.join(child)}), — п. «а» ч. 1 ст. 73 УК РФ"
        )
    listed = [o.article for o in offences if o.in_a1_list]
    if listed:
        reasons.append(f"преступление из перечня п. «а1» ч. 1 ст. 73 УК РФ ({'; '.join(listed)})")
    if reasons:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Назначено условное осуждение, но осуждённый признан виновным в преступлении, за "
            f"которое условное осуждение не назначается: {'; '.join(reasons)}.",
        )
    unknown = [
        o.article for o in offences if o.child_sexual_inviolability is None or o.in_a1_list is None
    ]
    if unknown:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, относится ли к перечням пп. «а», «а1» ч. 1 ст. 73 УК РФ: "
            f"{'; '.join(unknown)}.",
        )
    return result(
        CheckStatus.OK,
        "Ни одно преступление не относится к перечням пп. «а», «а1» ч. 1 ст. 73 УК РФ.",
    )


# --- Сводная проверка условного осуждения по ч. 1 и ч. 3 ст. 73 (используется анализом:
# src/services/sentence_checks): вид и срок наказания, п. «в» ч. 1 и испытательный срок ч. 3.
# Пункты «а», «а.1», «б» ч. 1 передаёт вызывающий (other_exclusions); подробные правила каталога —
# функции выше.
SENTENCE_NORM = "Условное осуждение: ч. 1, 3 ст. 73 УК РФ"
SENTENCE_SOURCE = (
    "УК РФ ст. 73, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "1fc6797cfe603f5b327aa4ea29644309db22717d/ (УК РФ ред. от 04.08.2026, сверено 28.10.2026)"
)
PROBATION_MIN_MONTHS = 6
PROBATION_MAX_SHORT_MONTHS = 36  # лишение свободы до одного года или более мягкое наказание
PROBATION_MAX_LONG_MONTHS = 60  # лишение свободы свыше одного года
EXCLUSION_ITEMS = {"а", "а.1", "б"}


class ConditionalKind(StrEnum):
    IMPRISONMENT = "imprisonment"
    CORRECTIONAL_LABOUR = "correctional_labour"
    MILITARY_RESTRICTION = "military_restriction"
    DISCIPLINARY_UNIT = "disciplinary_unit"
    OTHER = "other"  # любое иное наказание: условно не назначается


def probation_bounds(kind: ConditionalKind, months: int | None) -> tuple[int, int] | None:
    """Границы испытательного срока (мес.) по ч. 3 ст. 73; None — срок не известен."""
    if kind is ConditionalKind.IMPRISONMENT:
        if months is None:
            return None
        upper = PROBATION_MAX_LONG_MONTHS if months > 12 else PROBATION_MAX_SHORT_MONTHS
        return PROBATION_MIN_MONTHS, upper
    return PROBATION_MIN_MONTHS, PROBATION_MAX_SHORT_MONTHS


def check_conditional_sentence(
    *,
    conditional: bool,
    kind: ConditionalKind,
    imprisonment_months: int | None,
    probation_months: int | None,
    recidivism: Recidivism,
    other_exclusions: Iterable[str] = (),
) -> CheckResult:
    """Кандидатная проверка условного осуждения по ч. 1 и 3 ст. 73 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(SENTENCE_NORM, status, why, SENTENCE_SOURCE, NEEDS_LEGAL_REVIEW)

    if not conditional:
        return result(CheckStatus.OK, "Наказание назначено реально — ст. 73 УК РФ не применялась.")

    violations: list[str] = []
    gaps: list[str] = []
    if kind is ConditionalKind.OTHER:
        violations.append("этот вид наказания не может быть назначен условно (ч. 1 ст. 73)")
    elif kind is ConditionalKind.IMPRISONMENT:
        if imprisonment_months is None:
            gaps.append("срок лишения свободы не определён")
        elif imprisonment_months > MAX_CONDITIONAL_IMPRISONMENT_MONTHS:
            violations.append(
                f"лишение свободы {imprisonment_months} мес. — условно только до 8 лет "
                "(ч. 1 ст. 73)"
            )

    if recidivism in (Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS):
        violations.append("при опасном или особо опасном рецидиве (п. «в» ч. 1 ст. 73)")
    elif recidivism is Recidivism.UNKNOWN:
        gaps.append("вид рецидива не установлен (п. «в» ч. 1 ст. 73)")

    excluded = sorted(set(other_exclusions) & EXCLUSION_ITEMS)
    for item in excluded:
        violations.append(f"случай п. «{item}» ч. 1 ст. 73")

    bounds = probation_bounds(kind, imprisonment_months)
    if probation_months is None:
        gaps.append("испытательный срок не определён")
    elif bounds is not None:
        low, high = bounds
        if not low <= probation_months <= high:
            violations.append(
                f"испытательный срок {probation_months} мес. вне пределов {low}–{high} мес. "
                "(ч. 3 ст. 73)"
            )

    if violations:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Условное осуждение: " + "; ".join(violations) + ".",
        )
    if gaps:
        return result(CheckStatus.INSUFFICIENT_DATA, "Не проверено: " + "; ".join(gaps) + ".")
    return result(
        CheckStatus.OK,
        "Условное осуждение допустимо по виду и сроку наказания и рецидиву; испытательный срок в "
        "пределах ч. 3 ст. 73. Пункты «а», «а.1», «б» ч. 1 проверьте по составу и истории.",
    )
