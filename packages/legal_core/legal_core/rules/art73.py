# Domain Layer — п. «в» ч. 1 ст. 73 УК РФ «Условное осуждение».
# ч. 1: «... Условное осуждение не назначается: ... в) при опасном или особо опасном рецидиве.»
# (часть в ред. ФЗ от 16.10.2012 N 172-ФЗ). The bar is absolute: no circumstance of the case
# lifts it. Пленум ВС РФ № 58 от 22.12.2015, п. 62: for several offences the conditional
# decision is taken once, for the final punishment, so the caller passes the final decision.
# The kind of recidivism comes from art18 (the caller classifies it on the offence date).
# п. «б»: a grave or especially grave offence during probation or the unserved part after parole,
# the earlier punishment being for an intentional offence; the caller passes the periods.
# TODO(T4/T23): пп. «а», «а1» ч. 1 (offence list) and
# the general limits of ч. 1 (punishment kinds, imprisonment up to eight years) are not
# modelled here; the explanation says so instead of silently passing them.

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category
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
