# Domain Layer — п. «в» ч. 1 ст. 73 УК РФ «Условное осуждение».
# ч. 1: «... Условное осуждение не назначается: ... в) при опасном или особо опасном рецидиве.»
# (часть в ред. ФЗ от 16.10.2012 N 172-ФЗ). The bar is absolute: no circumstance of the case
# lifts it. Пленум ВС РФ № 58 от 22.12.2015, п. 62: for several offences the conditional
# decision is taken once, for the final punishment, so the caller passes the final decision.
# The kind of recidivism comes from art18 (the caller classifies it on the offence date).
# TODO(T4/T23): пп. «а», «а1», «б» ч. 1 (offence list, offence during probation / parole) and
# the general limits of ч. 1 (punishment kinds, imprisonment up to eight years) are not
# modelled here; the explanation says so instead of silently passing them.
from legal_core.checks import CheckResult, CheckStatus
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
