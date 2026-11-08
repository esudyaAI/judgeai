# Domain Layer — ч. 1 и ч. 3 ст. 58 УК РФ «Назначение осужденным к лишению свободы вида
# исправительного учреждения» (статья в ред. ФЗ от 09.03.2001 N 25-ФЗ; пп. «б», «в» ч. 1 —
# в ред. ФЗ от 08.12.2003 N 162-ФЗ) с разъяснениями Пленума ВС РФ от 29.05.2014 N 9
# (ред. от 26.11.2024 N 36): п. 2 (п. «а» ч. 1 — неосторожные, совокупность, тяжкое без лишения
# свободы), пп. 3–4 (мужчины, ранее отбывавшие, без рецидива), п. 8 (женщины), пп. 9–10
# (несовершеннолетние), п. 11 (кто «ранее отбывал»), п. 18 (условное осуждение).
# The law leaves no discretion except the motivated choice of a general-regime colony instead
# of a settlement colony (п. «а» ч. 1, ППВС № 9 п. 1), so the rule returns one institution.
# The caller supplies: the kind of recidivism (art18, on the offence date), whether the person
# previously served imprisonment in the sense of ППВС № 9 п. 11 (a fact, not computed here),
# the punishment of each offence of the aggregate. An unknown fact that matters → ``None``.
# Часть срока в тюрьме (ч. 2 и 2.1) — отдельное правило legal_core.rules.art58_prison.
# TODO(T4/T23): ч. 4 / ст. 78 УИК (изменение вида), ст. 74 УИК (СИЗО), п. 7 (новое преступление во
# время отбывания в тюрьме) are not modelled; the explanation says so.
from dataclasses import dataclass
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art58.institution"

NORM = "Вид исправительного учреждения: ч. 1 и ч. 3 ст. 58 УК РФ"
SOURCE = (
    "УК РФ ст. 58 (ред. ФЗ от 09.03.2001 N 25-ФЗ; пп. «б», «в» ч. 1 — ФЗ от 08.12.2003 "
    "N 162-ФЗ) — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891"
    "&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735"
    "b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23); Пленум ВС РФ от "
    "29.05.2014 N 9 (ред. от 26.11.2024 N 36), пп. 1–4, 8–11, 18 — официальный файл vsrf.ru, "
    "sha256 3d8e7b726f68ef3172f859e8ee88320d5102a2e94c13298ef8d9d6f8c37ed73a"
)


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class Institution(StrEnum):
    SETTLEMENT = "settlement"  # колония-поселение
    GENERAL = "general"  # исправительная колония общего режима
    STRICT = "strict"  # исправительная колония строгого режима
    SPECIAL = "special"  # исправительная колония особого режима
    EDUCATIONAL = "educational"  # воспитательная колония


NAMES = {
    Institution.SETTLEMENT: "колония-поселение",
    Institution.GENERAL: "исправительная колония общего режима",
    Institution.STRICT: "исправительная колония строгого режима",
    Institution.SPECIAL: "исправительная колония особого режима",
    Institution.EDUCATIONAL: "воспитательная колония",
}

# Severity order of the adult institutions, used to combine the minor and adult periods.
_ORDER = [Institution.SETTLEMENT, Institution.GENERAL, Institution.STRICT, Institution.SPECIAL]

_NOT_CHECKED = (
    "Назначение части срока в тюрьме (ч. 2 и 2.1 ст. 58 УК РФ) проверяется отдельным правилом."
)


@dataclass(frozen=True)
class OffenceForRegime:
    """One offence of the verdict (aggregate): its guilt, category and punishment.

    ``committed_as_minor`` — committed before the age of eighteen (ППВС № 9 п. 10);
    ``imprisonment`` — imprisonment was imposed for this offence (ППВС № 9 п. 2 «в»).
    """

    guilt: Guilt
    category: Category
    committed_as_minor: bool
    imprisonment: bool


def _male_adult_period(
    top: Category, previously_served: bool | None, recidivism: Recidivism
) -> Institution | None:
    if recidivism is Recidivism.ESPECIALLY_DANGEROUS:
        return Institution.SPECIAL  # п. «г» ч. 1
    if recidivism is Recidivism.UNKNOWN:
        return None
    if recidivism is not Recidivism.NONE:
        if previously_served is None:
            return None
        if previously_served:
            return Institution.STRICT  # п. «в» ч. 1: рецидив, ранее отбывал
    if top is Category.ESPECIALLY_GRAVE:
        return Institution.STRICT  # п. «в» ч. 1; ППВС № 9 п. 4
    if previously_served is None:
        return None
    if top is Category.GRAVE or previously_served:
        return Institution.GENERAL  # п. «б» ч. 1; ППВС № 9 п. 3
    return Institution.SETTLEMENT  # п. «а» ч. 1


def required_institution(
    offences: list[OffenceForRegime],
    *,
    sex: Sex | None,
    minor_at_sentencing: bool | None,
    life_imprisonment: bool,
    previously_served: bool | None,
    recidivism: Recidivism,
) -> Institution | None:
    """The institution ст. 58 requires for real imprisonment; ``None`` — a needed fact is unknown.

    For ``Institution.SETTLEMENT`` the court may instead choose a general-regime colony with
    stated reasons (п. «а» ч. 1); ``check_correctional_institution`` handles that choice.
    """
    jailed = [o for o in offences if o.imprisonment]
    if not jailed:
        raise ValueError("art. 58 applies only when imprisonment is imposed for some offence")
    if minor_at_sentencing is None:
        return None
    if minor_at_sentencing:
        return Institution.EDUCATIONAL  # ч. 3; ППВС № 9 п. 9
    if life_imprisonment:
        if sex is Sex.FEMALE:
            raise ValueError("life imprisonment is not imposed on women (ч. 2 ст. 57 УК РФ)")
        return None if sex is None else Institution.SPECIAL  # п. «г» ч. 1
    intentional = [o for o in jailed if o.guilt is Guilt.INTENTIONAL]
    if not intentional:
        return Institution.SETTLEMENT  # п. «а» ч. 1; ППВС № 9 п. 2 «а»
    if sex is None:
        return None
    as_minor = [o for o in intentional if o.committed_as_minor]
    as_adult = [o for o in intentional if not o.committed_as_minor]
    # ППВС № 9 п. 10: тяжкое/особо тяжкое до 18 лет при совершеннолетии к приговору — общий режим.
    serious_as_minor = any(o.category >= Category.GRAVE for o in as_minor)
    floor = Institution.GENERAL if serious_as_minor else Institution.SETTLEMENT
    if not as_adult:
        return floor
    top = max(o.category for o in as_adult)
    if sex is Sex.FEMALE:
        # п. «б» ч. 1 и ППВС № 9 п. 8: тяжкие и особо тяжкие — общий режим при любом рецидиве,
        # в остальных случаях — по п. «а».
        adult = Institution.GENERAL if top >= Category.GRAVE else Institution.SETTLEMENT
    else:
        adult = _male_adult_period(top, previously_served, recidivism)
        if adult is None:
            return None
    return max(floor, adult, key=_ORDER.index)


def check_correctional_institution(
    offences: list[OffenceForRegime],
    *,
    conditional: bool | None,
    draft_institution: Institution | None,
    general_instead_of_settlement_motivated: bool | None,
    sex: Sex | None,
    minor_at_sentencing: bool | None,
    life_imprisonment: bool,
    previously_served: bool | None,
    recidivism: Recidivism,
) -> CheckResult:
    """Candidate check: the draft names the institution ст. 58 requires.

    ``conditional`` — the final punishment is conditional (ст. 73), ``None`` — not extracted;
    ``draft_institution`` — the institution named in the draft, ``None`` — none named;
    ``general_instead_of_settlement_motivated`` — the draft gives reasons for a general-regime
    colony instead of a settlement colony (п. «а» ч. 1), ``None`` — not extracted.
    """

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)

    if conditional is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначено ли в проекте наказание условно (ст. 73 УК РФ).",
        )
    if conditional:
        if draft_institution is None:
            return result(
                CheckStatus.OK,
                "Наказание назначено условно — вид исправительного учреждения не назначается "
                "(ППВС № 9 п. 18).",
            )
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Наказание назначено условно, но в проекте указана {NAMES[draft_institution]}: при "
            "условном осуждении вид исправительного учреждения не назначается (ППВС № 9 п. 18).",
        )
    if draft_institution is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "В проекте не найден вид исправительного учреждения (ст. 58 УК РФ).",
        )
    required = required_institution(
        offences,
        sex=sex,
        minor_at_sentencing=minor_at_sentencing,
        life_imprisonment=life_imprisonment,
        previously_served=previously_served,
        recidivism=recidivism,
    )
    if required is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлены сведения, нужные для выбора вида учреждения по ст. 58 УК РФ "
            "(пол, возраст к приговору, отбывание лишения свободы ранее или вид рецидива).",
        )
    if draft_institution is required:
        return result(
            CheckStatus.OK,
            f"Вид учреждения соответствует ст. 58 УК РФ: {NAMES[required]}. {_NOT_CHECKED}",
        )
    if required is Institution.SETTLEMENT and draft_institution is Institution.GENERAL:
        if general_instead_of_settlement_motivated is None:
            return result(
                CheckStatus.INSUFFICIENT_DATA,
                "Вместо колонии-поселения назначена колония общего режима; не установлено, "
                "приведены ли мотивы (п. «а» ч. 1 ст. 58 УК РФ).",
            )
        if general_instead_of_settlement_motivated:
            return result(
                CheckStatus.OK,
                "Вместо колонии-поселения назначена колония общего режима с указанием мотивов "
                f"(п. «а» ч. 1 ст. 58 УК РФ). {_NOT_CHECKED}",
            )
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Вместо колонии-поселения назначена колония общего режима без указания мотивов: "
            "п. «а» ч. 1 ст. 58 УК РФ и ППВС № 9 п. 2 требуют мотивировать это решение.",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"В проекте назначена {NAMES[draft_institution]}, а по ст. 58 УК РФ при установленных "
        f"данных — {NAMES[required]}. {_NOT_CHECKED}",
    )
