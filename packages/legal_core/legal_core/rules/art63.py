# Domain Layer — п. «а» ч. 1 и ч. 2 ст. 63 УК РФ «Обстоятельства, отягчающие наказание».
# ч. 1: «Отягчающими обстоятельствами признаются: а) рецидив преступлений; ...» — the list is
# closed and mandatory: a recidivism established under ст. 18 has to be recognized.
# ч. 2: a circumstance that is an element of the offence is not counted again as aggravating.
# Пленум ВС РФ № 58 от 22.12.2015, п. 32 (ред. Пленума № 40 от 23.12.2025): e.g. a prior
# conviction that grounds the administrative supervision under ст. 314.1 is not counted again.
# Which prior convictions are an element of the offence is decided by the caller: it classifies
# recidivism (art18) without those convictions and reports that it excluded them.
# TODO(T4/T23): ч. 1.1 (intoxication) and the other points of ч. 1 are not modelled here.
from legal_core.checks import CheckResult, CheckStatus
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True

NORM = "Рецидив как отягчающее обстоятельство: п. «а» ч. 1, ч. 2 ст. 63 УК РФ"
SOURCE = (
    "УК РФ ст. 63 (текст по https://rulaws.ru/uk/Razdel-III/Glava-10/Statya-63, сверено "
    "28.10.2026; официальную редакцию сверить в T23); Пленум ВС РФ от 22.12.2015 N 58 "
    "(ред. от 23.12.2025), п. 32 — https://www.consultant.ru/document/cons_doc_LAW_190932/"
    "90d767f9a638a7bac2730af001ce66cc8329095b/"
)

_KIND_NAMES = {
    Recidivism.SIMPLE: "простой",
    Recidivism.DANGEROUS: "опасный",
    Recidivism.ESPECIALLY_DANGEROUS: "особо опасный",
}


def check_recidivism_aggravation(
    *,
    recidivism: Recidivism,
    recognized_in_draft: Recidivism | None,
    element_convictions_excluded: bool,
) -> CheckResult:
    """Candidate check: is recidivism recognized as aggravating exactly when it exists.

    ``recidivism`` — the kind classified by ст. 18 over prior convictions that are not an
    element of the offence. ``recognized_in_draft`` — what the draft recognizes as aggravating:
    ``NONE`` — not recognized, ``UNKNOWN`` — recognized without naming the kind, a kind —
    recognized with that kind, ``None`` — the draft position was not extracted.
    """

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW)

    if recognized_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, признан ли в проекте рецидив отягчающим обстоятельством.",
        )
    if recidivism is Recidivism.UNKNOWN:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Вид рецидива не установлен — п. «а» ч. 1 ст. 63 УК РФ не проверен.",
        )
    recognized = recognized_in_draft is not Recidivism.NONE

    if recidivism is Recidivism.NONE:
        if not recognized:
            return result(CheckStatus.OK, "Рецидива нет, отягчающим он не признан.")
        if element_convictions_excluded:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                "Рецидив признан отягчающим, но судимость является признаком состава "
                "преступления и повторно не учитывается (ч. 2 ст. 63 УК РФ, Пленум ВС РФ "
                "N 58, п. 32); других судимостей, образующих рецидив, нет.",
            )
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Рецидив признан отягчающим, но судимости не образуют рецидива по ст. 18 УК РФ.",
        )

    kind = _KIND_NAMES[recidivism]
    if not recognized:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Есть {kind} рецидив (ст. 18 УК РФ), но он не признан отягчающим "
            "обстоятельством (п. «а» ч. 1 ст. 63 УК РФ).",
        )
    if recognized_in_draft is Recidivism.UNKNOWN:
        return result(
            CheckStatus.OK,
            f"Рецидив признан отягчающим; вид в проекте не назван — по ст. 18 УК РФ это {kind} "
            "рецидив.",
        )
    if recognized_in_draft is not recidivism:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"В проекте указан {_KIND_NAMES[recognized_in_draft]} рецидив, по ст. 18 УК РФ — "
            f"{kind}.",
        )
    return result(
        CheckStatus.OK, f"{kind.capitalize()} рецидив признан отягчающим обстоятельством."
    )
