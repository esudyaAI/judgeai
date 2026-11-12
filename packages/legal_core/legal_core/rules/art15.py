# Domain Layer — ст. 15 УК РФ «Категории преступлений».
# Written against: УК РФ от 13.06.1996 N 63-ФЗ, ред. от 04.08.2026 (consultant.ru).
# The page notes it includes amendments not yet in force — verify the edition in force
# on the crime date before relying on this (TODO: edition-aware rules, task T4/ст. 9-10).
from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category, Guilt, ImposedPunishment, SanctionCeiling

SOURCE = (
    "ст. 15 УК РФ, ред. от 04.08.2026, "
    "https://www.consultant.ru/document/cons_doc_LAW_10699/a0182fc43a8bbf8974658cda72c860ddfb210c52/"
)
_NORM_PART6 = "ч. 6 ст. 15 УК РФ"
RULE_KEY = "art15.category"
_YEAR = 12

# Upper imprisonment bound (months, inclusive) per category and form of guilt, ч. 2–4.
_LIMITS: dict[Guilt, list[tuple[int, Category]]] = {
    Guilt.INTENTIONAL: [
        (3 * _YEAR, Category.SMALL),
        (5 * _YEAR, Category.MEDIUM),
        (10 * _YEAR, Category.GRAVE),
    ],
    Guilt.NEGLIGENT: [
        (3 * _YEAR, Category.SMALL),
        (10 * _YEAR, Category.MEDIUM),
        (15 * _YEAR, Category.GRAVE),
    ],
}

# ч. 6: max imposed imprisonment allowing the change, keyed by the ORIGINAL category.
_PART6_MAX_IMPOSED = {
    Category.MEDIUM: 3 * _YEAR,
    Category.GRAVE: 5 * _YEAR,
    Category.ESPECIALLY_GRAVE: 7 * _YEAR,
}


def categorize(guilt: Guilt, ceiling: SanctionCeiling) -> Category:
    """Category of a crime by its form of guilt and the sanction's maximum (ч. 2–5)."""
    months = ceiling.max_imprisonment_months
    if months is None:
        return Category.SMALL  # ч. 2: maximum does not exceed 3 years of imprisonment
    if not ceiling.harsher_than_imprisonment:
        for limit, category in _LIMITS[guilt]:
            if months <= limit:
                return category
    if guilt is Guilt.INTENTIONAL:
        return Category.ESPECIALLY_GRAVE  # ч. 5
    raise ValueError("art. 15 defines no category for a negligent crime above 15 years")


def check_category_change(
    *,
    original: Category,
    claimed: Category,
    has_mitigating: bool,
    has_aggravating: bool,
    imposed: ImposedPunishment,
) -> CheckResult:
    """Is the court's change of category under ч. 6 consistent with its conditions?"""

    def violation(why: str) -> CheckResult:
        return CheckResult(
            _NORM_PART6, CheckStatus.POSSIBLE_VIOLATION, why, SOURCE, rule_key=RULE_KEY
        )

    if claimed.value >= original.value:
        return violation("Категория может быть изменена только на менее тяжкую.")
    if original.value - claimed.value > 1:
        return violation("Категорию можно снизить не более чем на одну ступень.")
    if not has_mitigating:
        return violation("Изменение категории требует наличия смягчающих обстоятельств.")
    if has_aggravating:
        return violation("При наличии отягчающих обстоятельств категорию изменять нельзя.")
    limit = _PART6_MAX_IMPOSED[original]
    months = imposed.imprisonment_months
    if months is not None and months > limit:
        return violation(
            f"Назначено {months} мес. лишения свободы при пределе {limit} мес. "
            f"для изменения категории этого преступления."
        )
    return CheckResult(
        _NORM_PART6,
        CheckStatus.OK,
        "Условия изменения категории соблюдены.",
        SOURCE,
        rule_key=RULE_KEY,
    )
