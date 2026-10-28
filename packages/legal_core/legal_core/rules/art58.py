# Domain Layer — ч. 1 ст. 58 УК РФ: вид исправительного учреждения при лишении свободы.
# п. «а» — колония-поселение: неосторожные преступления; умышленные небольшой и средней
#   тяжести, если ранее не отбывал лишение свободы (суд может назначить общий режим с
#   мотивировкой);
# п. «б» — общий режим: мужчинам за тяжкие, если ранее не отбывал; женщинам за тяжкие и особо
#   тяжкие, в том числе при любом виде рецидива;
# п. «в» — строгий режим: мужчинам за особо тяжкие, если ранее не отбывал; мужчинам при рецидиве
#   или опасном рецидиве, если ранее отбывал лишение свободы;
# п. «г» — особый режим: мужчинам при пожизненном лишении свободы и особо опасном рецидиве.
# Не смоделировано (TODO T4/T23): ч. 2 и 2.1 (часть срока в тюрьме), несовершеннолетние
# (воспитательная колония), случаи вне прямого текста ч. 1 — например, мужчина, ранее отбывавший
# лишение свободы, без рецидива; для них ожидаемый вид не выдаётся (разъяснения ППВС от 29.05.2014
# N 9 — предмет T23).

from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
NORM = "Вид исправительного учреждения: ч. 1 ст. 58 УК РФ"
SOURCE = (
    "УК РФ ст. 58, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "dcc1c2f0397c7d89fcdf6e56fc2de57e14f4f864/ (УК РФ ред. от 04.08.2026, сверено 28.10.2026)"
)


class Regime(StrEnum):
    SETTLEMENT = "settlement"  # колония-поселение
    GENERAL = "general"  # общий режим
    STRICT = "strict"  # строгий режим
    SPECIAL = "special"  # особый режим


REGIME_RU = {
    Regime.SETTLEMENT: "колония-поселение",
    Regime.GENERAL: "колония общего режима",
    Regime.STRICT: "колония строгого режима",
    Regime.SPECIAL: "колония особого режима",
}


def expected_regimes(
    *,
    guilt: Guilt,
    category: Category,
    male: bool,
    recidivism: Recidivism,
    served_imprisonment_before: bool,
    life_imprisonment: bool = False,
) -> tuple[frozenset[Regime], bool] | None:
    """Допустимые виды учреждения и признак «отступление требует мотивировки».

    Возвращает (виды, нужна_мотивировка_для_второго) или None, если случай вне текста ч. 1.
    Для п. «а» допустим и общий режим, но только с мотивировкой суда.
    """
    if male and (life_imprisonment or recidivism is Recidivism.ESPECIALLY_DANGEROUS):
        return frozenset({Regime.SPECIAL}), False
    if guilt is Guilt.NEGLIGENT or (
        category in (Category.SMALL, Category.MEDIUM) and not served_imprisonment_before
    ):
        return frozenset({Regime.SETTLEMENT, Regime.GENERAL}), True
    if not male:
        if category in (Category.GRAVE, Category.ESPECIALLY_GRAVE):
            return frozenset({Regime.GENERAL}), False
        return None
    if served_imprisonment_before and recidivism in (Recidivism.SIMPLE, Recidivism.DANGEROUS):
        return frozenset({Regime.STRICT}), False
    if not served_imprisonment_before:
        if category is Category.GRAVE:
            return frozenset({Regime.GENERAL}), False
        if category is Category.ESPECIALLY_GRAVE:
            return frozenset({Regime.STRICT}), False
    return None


def check_regime(
    *,
    imposed: Regime | None,
    guilt: Guilt | None,
    category: Category | None,
    male: bool | None,
    recidivism: Recidivism,
    served_imprisonment_before: bool | None,
    life_imprisonment: bool = False,
) -> CheckResult:
    """Кандидатная проверка назначенного вида учреждения по ч. 1 ст. 58 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW)

    missing = [
        name
        for name, value in (
            ("назначенный вид учреждения", imposed),
            ("форма вины", guilt),
            ("категория преступления", category),
            ("пол осуждённого", male),
            ("отбывал ли ранее лишение свободы", served_imprisonment_before),
        )
        if value is None
    ]
    if recidivism is Recidivism.UNKNOWN:
        missing.append("вид рецидива")
    if missing:
        return result(CheckStatus.INSUFFICIENT_DATA, "Не определены: " + ", ".join(missing) + ".")

    expected = expected_regimes(
        guilt=guilt,
        category=category,
        male=male,
        recidivism=recidivism,
        served_imprisonment_before=served_imprisonment_before,
        life_imprisonment=life_imprisonment,
    )
    if expected is None:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Случай прямо не описан ч. 1 ст. 58 — нужна проверка по разъяснениям Пленума ВС.",
        )
    regimes, motivated_alternative = expected
    names = ", ".join(REGIME_RU[r] for r in Regime if r in regimes)
    if imposed not in regimes:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначена {REGIME_RU[imposed]}, по ч. 1 ст. 58 ожидается: {names}.",
        )
    if motivated_alternative and imposed is Regime.GENERAL:
        return result(
            CheckStatus.OK,
            "Вместо колонии-поселения назначен общий режим — допустимо по п. «а» ч. 1 ст. 58 "
            "только с мотивировкой; проверьте её в приговоре.",
        )
    return result(CheckStatus.OK, f"Назначена {REGIME_RU[imposed]} — соответствует ч. 1 ст. 58.")
