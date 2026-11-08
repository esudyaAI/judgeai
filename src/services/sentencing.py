"""Deterministic sentencing arithmetic (no LLM).

Adapter from API schemas to the domain rule: ч. 1 ст. 62 УК РФ lives in
``legal_core.rules.art62``; this module only maps ``Circumstance`` to cited norms.
"""

from legal_core.rules.art62 import has_part1_mitigation, part1_limit_months

from src.schemas.analysis import Circumstance


def has_art62_part1_mitigation(mitigating: list[Circumstance]) -> bool:
    return has_part1_mitigation(c.norm or "" for c in mitigating)


def art62_part1_limit(
    sanction_max_months: int,
    mitigating: list[Circumstance],
    aggravating: list[Circumstance],
    *,
    sanction_has_life_or_death: bool = False,
) -> int | None:
    """Upper limit in whole months, or None when ч. 1 ст. 62 does not apply."""
    return part1_limit_months(
        sanction_max_months,
        (c.norm or "" for c in mitigating),
        has_aggravating=bool(aggravating),
        sanction_has_life_or_death=sanction_has_life_or_death,
    )
