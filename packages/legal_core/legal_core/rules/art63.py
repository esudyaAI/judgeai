# Domain Layer — п. «а» ч. 1 и ч. 2 ст. 63 УК РФ «Обстоятельства, отягчающие наказание».
# ч. 1: «Отягчающими обстоятельствами признаются: а) рецидив преступлений; ...» — the list is
# closed and mandatory: a recidivism established under ст. 18 has to be recognized.
# ч. 2: a circumstance that is an element of the offence is not counted again as aggravating.
# Пленум ВС РФ № 58 от 22.12.2015, п. 32 (ред. Пленума № 40 от 23.12.2025): e.g. a prior
# conviction that grounds the administrative supervision under ст. 314.1 is not counted again.
# Which prior convictions are an element of the offence is decided by the caller: it classifies
# recidivism (art18) without those convictions and reports that it excluded them.
# ч. 1.1 (intoxication) — check_intoxication_aggravation below (T4.14).
# TODO(T4/T23): the other points of ч. 1 are not modelled here.
from dataclasses import dataclass

from legal_core.checks import CheckResult, CheckStatus
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art63.recidivism_aggravating"

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
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)

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


# ч. 1.1 ст. 63 УК РФ (введена ФЗ от 21.10.2013 N 270-ФЗ, в ред. ФЗ от 03.07.2016 N 328-ФЗ):
# «Судья (суд), назначающий наказание, в зависимости от характера и степени общественной
# опасности преступления, обстоятельств его совершения и личности виновного может признать
# отягчающим обстоятельством совершение преступления в состоянии опьянения…». It is a right of
# the court, so non-recognition is never a finding. Пленум ВС РФ № 58, п. 31: the state by itself
# is not a ground, the motives must be given in the описательно-мотивировочная часть; п. 30 and
# ч. 2 ст. 63: a circumstance that is an element of the offence (e.g. п. «а» ч. 2 ст. 264,
# ст. 264.1) is not counted again. Which offences have intoxication as an element depends on the
# qualification and the edition — the caller decides; no article numbers are hard-coded here.
INTOXICATION_RULE_KEY = "art63.intoxication_aggravating"
INTOXICATION_NORM = "Состояние опьянения как отягчающее обстоятельство: ч. 1.1 и ч. 2 ст. 63 УК РФ"
INTOXICATION_SOURCE = (
    "УК РФ ст. 63 ч. 1.1 (введена ФЗ от 21.10.2013 N 270-ФЗ, в ред. ФЗ от 03.07.2016 N 328-ФЗ), "
    "ч. 2 — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, "
    "получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b "
    "(статус unreviewed); Пленум ВС РФ от 22.12.2015 N 58 (ред. от 23.12.2025), пп. 30, 31 — "
    "официальный файл vsrf.ru, получен 27.10.2026, sha256 "
    "3e244ff596b2a779fc32d5f61aa6567680f7a52540b9ab3c7f0be73753b77c7b (статус unreviewed)"
)


@dataclass(frozen=True)
class IntoxicationFacts:
    """What the draft says about intoxication; ``None`` — the fact was not extracted.

    ``recognized_in_draft`` — intoxication is recognized as an aggravating circumstance.
    ``established`` — the state at the moment of the offence is established by the court.
    ``offence_element`` — intoxication is an element of the offence as qualified (ч. 2 ст. 63).
    ``motives_given`` — the описательно-мотивировочная часть gives the motives (п. 31).
    """

    recognized_in_draft: bool | None
    established: bool | None
    offence_element: bool | None
    motives_given: bool | None


def check_intoxication_aggravation(facts: IntoxicationFacts) -> CheckResult:
    """Candidate check of ч. 1.1 ст. 63: intoxication recognized as aggravating lawfully."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(
            INTOXICATION_NORM,
            status,
            why,
            INTOXICATION_SOURCE,
            NEEDS_LEGAL_REVIEW,
            INTOXICATION_RULE_KEY,
        )

    if facts.recognized_in_draft is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, признано ли в проекте состояние опьянения отягчающим "
            "обстоятельством (ч. 1.1 ст. 63 УК РФ).",
        )
    if not facts.recognized_in_draft:
        return result(
            CheckStatus.OK,
            "Состояние опьянения отягчающим не признано — это право суда (ч. 1.1 ст. 63 УК РФ).",
        )

    violations: list[str] = []
    if facts.offence_element:
        violations.append(
            "состояние опьянения является признаком состава преступления и повторно не "
            "учитывается (ч. 2 ст. 63 УК РФ, Пленум ВС РФ N 58, п. 30)"
        )
    if facts.established is False:
        violations.append("состояние опьянения в момент совершения преступления не установлено")
    if facts.motives_given is False:
        violations.append(
            "не приведены мотивы признания состояния опьянения отягчающим — само по себе "
            "оно не является основанием (Пленум ВС РФ N 58, п. 31)"
        )
    if violations:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Состояние опьянения признано отягчающим, но " + "; ".join(violations) + ".",
        )

    unknown = [
        name
        for name, value in (
            ("установлено ли состояние опьянения в момент преступления", facts.established),
            ("является ли оно признаком состава преступления", facts.offence_element),
            ("приведены ли мотивы признания", facts.motives_given),
        )
        if value is None
    ]
    if unknown:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Состояние опьянения признано отягчающим; не установлено: " + "; ".join(unknown) + ".",
        )
    return result(
        CheckStatus.OK,
        "Состояние опьянения признано отягчающим с приведением мотивов; признаком состава "
        "преступления оно не является.",
    )
