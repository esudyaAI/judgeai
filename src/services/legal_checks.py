"""Conservative bridge from quoted model extractions to deterministic domain rules.

Exact quote matching establishes provenance, not semantic correctness or law edition.
Every candidate therefore requires human review; no inference from absent history.
"""

from legal_core.entities import Category, Guilt, SanctionCeiling
from legal_core.rules.art15 import SOURCE as ART15_SOURCE
from legal_core.rules.art15 import categorize
from legal_core.rules.art18 import SOURCE as ART18_SOURCE
from legal_core.rules.art18 import CurrentOffence, PriorConviction, classify_recidivism

from src.schemas.analysis import CitedFact, LegalCheck, LegalFacts

_CATEGORIES = {
    "small": Category.SMALL,
    "medium": Category.MEDIUM,
    "grave": Category.GRAVE,
    "especially_grave": Category.ESPECIALLY_GRAVE,
}


def _value(fact: CitedFact | None, text: str, kind: type):
    if fact is None or fact.quote not in text or type(fact.value) is not kind:
        raise ValueError("missing, unsupported or mistyped fact")
    return fact.value


def build_legal_checks(
    facts: LegalFacts | None,
    source_text: str,
    statutory_ceiling: SanctionCeiling | None = None,
) -> list[LegalCheck]:
    """statutory_ceiling comes from the imported УК РФ text; it replaces model-cited sanctions."""
    results = []
    for norm, source in [("ст. 15 УК РФ", ART15_SOURCE), ("ст. 18 УК РФ", ART18_SOURCE)]:
        check = LegalCheck(
            norm=norm,
            source=source,
            status="insufficient_data",
            explanation="Недостаточно подтверждённых фактов; правовой вывод не сделан.",
        )
        try:
            if facts is None:
                raise ValueError("no legal facts")
            guilt = Guilt(_value(facts.guilt, source_text, str))
            evidence = [facts.guilt.quote]
            if norm == "ст. 15 УК РФ":
                if statutory_ceiling is not None:
                    ceiling = statutory_ceiling
                else:
                    months = _value(facts.sanction_max_months, source_text, int)
                    harsher = _value(facts.harsher_than_imprisonment, source_text, bool)
                    ceiling = SanctionCeiling(months, harsher)
                    evidence += [
                        facts.sanction_max_months.quote,
                        facts.harsher_than_imprisonment.quote,
                    ]
                category = categorize(guilt, ceiling)
                check.value = next(key for key, val in _CATEGORIES.items() if val == category)
                check.explanation = (
                    "Предварительная категория по процитированным данным. Проверьте санкцию "
                    "статьи, дату преступления и применимую редакцию закона."
                )
            else:
                category = _CATEGORIES[_value(facts.category, source_text, str)]
                real = _value(facts.real_imprisonment, source_text, bool)
                complete = _value(facts.history_complete, source_text, bool)
                if not complete:
                    raise ValueError("incomplete history")
                evidence += [
                    facts.category.quote,
                    facts.real_imprisonment.quote,
                    facts.history_complete.quote,
                ]
                priors = []
                for item in facts.prior_convictions:
                    values = {}
                    for name in PriorConviction.__dataclass_fields__:
                        kind = str if name in ("judgment_id", "guilt", "category") else bool
                        values[name] = _value(item.get(name), source_text, kind)
                        evidence.append(item[name].quote)
                    values["guilt"] = Guilt(values["guilt"])
                    values["category"] = _CATEGORIES[values["category"]]
                    priors.append(PriorConviction(**values))
                check.value = classify_recidivism(
                    CurrentOffence(guilt, category, real),
                    priors,
                    history_complete=complete,
                ).value
                check.explanation = (
                    "Предварительный вид рецидива. Проверьте полноту сведений о судимостях, "
                    "отдельность приговоров, их действительность и все даты на момент преступления."
                )
            check.status = "ok"
            check.evidence = list(dict.fromkeys(evidence))
        except (ValueError, KeyError):
            pass
        results.append(check)
    return results
