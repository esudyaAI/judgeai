"""Art. 18 candidate classification, requiring human legal review.

Sources checked 2026-10-27: Criminal Code art.18, edition 2026-08-04;
Plenum 58, para.46.1 as amended by Plenum 40 (2025-12-23).
Edition on the offence date and validity of prior convictions are supplied by the caller.
"""

from dataclasses import dataclass
from enum import StrEnum

from legal_core.entities import Category, Guilt

SOURCE = (
    "https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "4ae34ba05e23456a1e99b9163a0703c0f4e125a4/; "
    "https://www.vsrf.ru/documents/own/35291/ (2025-12-23, para.46.1)"
)


RULE_KEY = "art18.recidivism"


class Recidivism(StrEnum):
    UNKNOWN = "unknown"
    NONE = "none"
    SIMPLE = "simple"
    DANGEROUS = "dangerous"
    ESPECIALLY_DANGEROUS = "especially_dangerous"


@dataclass(frozen=True)
class CurrentOffence:
    guilt: Guilt
    category: Category
    real_imprisonment: bool


@dataclass(frozen=True)
class PriorConviction:
    # One entry per separate judgment, not per count within a judgment.
    judgment_id: str
    guilt: Guilt
    category: Category
    adult_at_offence: bool
    active_at_offence: bool
    convicted_before_offence: bool
    imprisoned_by_sentence: bool
    conditional_or_deferred: bool
    revoked_and_sent_before_offence: bool

    @property
    def eligible(self) -> bool:
        return (
            self.guilt == Guilt.INTENTIONAL
            and self.category != Category.SMALL
            and self.adult_at_offence
            and self.active_at_offence
            and self.convicted_before_offence
            and (not self.conditional_or_deferred or self.revoked_and_sent_before_offence)
        )


def classify_recidivism(
    current: CurrentOffence,
    priors: list[PriorConviction],
    *,
    history_complete: bool,
) -> Recidivism:
    if len({p.judgment_id for p in priors}) != len(priors):
        raise ValueError("one entry per distinct judgment required")
    if current.guilt == Guilt.NEGLIGENT:
        return Recidivism.NONE
    if not history_complete:
        return Recidivism.UNKNOWN
    eligible = [p for p in priors if p.eligible]
    if not eligible:
        return Recidivism.NONE
    serious = [p for p in eligible if p.category >= Category.GRAVE]
    real_serious = [p for p in serious if p.imprisoned_by_sentence]
    medium = [p for p in eligible if p.category == Category.MEDIUM and p.imprisoned_by_sentence]
    if current.category == Category.ESPECIALLY_GRAVE:
        if len([p for p in eligible if p.category == Category.GRAVE]) >= 2 or any(
            p.category == Category.ESPECIALLY_GRAVE for p in eligible
        ):
            return Recidivism.ESPECIALLY_DANGEROUS
        if real_serious or len(medium) >= 2:
            return Recidivism.DANGEROUS
    if current.category == Category.GRAVE:
        if current.real_imprisonment and len(real_serious) >= 2:
            return Recidivism.ESPECIALLY_DANGEROUS
        if real_serious or (current.real_imprisonment and len(medium) >= 2):
            return Recidivism.DANGEROUS
    return Recidivism.SIMPLE
