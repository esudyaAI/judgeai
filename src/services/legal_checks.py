"""Conservative bridge from quoted model extractions to deterministic domain rules.

Exact quote matching establishes provenance, not semantic correctness or law edition.
Every candidate therefore requires human review; no inference from absent history.
"""

import re

from legal_core.entities import Category, Guilt, SanctionCeiling
from legal_core.precedents import Recidivism
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


_INTENT = re.compile(r"[^.\n]{0,160}\bумышленн\w*[^.\n]{0,160}", re.IGNORECASE)
_NEGLIGENCE = re.compile(r"[^.\n]{0,160}\bпо\s+неосторожности[^.\n]{0,160}", re.IGNORECASE)


def guilt_from_text(text: str) -> CitedFact | None:
    """Form of guilt quoted from the verdict itself when the model cited none; nothing when the
    text names both forms (several offences may differ) or neither."""
    intent, negligence = _INTENT.search(text or ""), _NEGLIGENCE.search(text or "")
    if bool(intent) == bool(negligence):
        return None
    match = intent or negligence
    value = Guilt.INTENTIONAL if intent else Guilt.NEGLIGENT
    return CitedFact(value=value.value, quote=match.group(0).strip())


def _value(fact: CitedFact | None, text: str, kind: type):
    if fact is None or fact.quote not in text or type(fact.value) is not kind:
        raise ValueError("missing, unsupported or mistyped fact")
    return fact.value


def build_legal_checks(
    facts: LegalFacts | None,
    source_text: str,
    statutory_ceiling: SanctionCeiling | None = None,
    extracted_recidivism: Recidivism | None = None,
    recidivism_quote: str = "",
    extracted_source_text: str | None = None,
    text_guilt: CitedFact | None = None,
) -> list[LegalCheck]:
    """statutory_ceiling comes from the imported УК РФ text; it replaces model-cited sanctions.
    text_guilt (quoted from extracted_source_text) is used when the model cited no guilt."""
    full_text = extracted_source_text if extracted_source_text is not None else source_text
    results = []
    for norm, source in [("ст. 15 УК РФ", ART15_SOURCE), ("ст. 18 УК РФ", ART18_SOURCE)]:
        check = LegalCheck(
            norm=norm,
            source=source,
            status="insufficient_data",
            explanation="Недостаточно подтверждённых фактов; правовой вывод не сделан.",
        )
        try:
            cited = facts.guilt if facts is not None else None
            if cited is not None:
                guilt = Guilt(_value(cited, source_text, str))
            elif norm == "ст. 15 УК РФ" and statutory_ceiling is not None and text_guilt:
                cited = text_guilt
                guilt = Guilt(_value(cited, full_text, str))
            else:
                raise ValueError("no cited guilt")
            evidence = [cited.quote]
            if norm == "ст. 15 УК РФ":
                if statutory_ceiling is None:
                    # The sanction maximum is never taken from the model: only the imported
                    # УК text can categorise the offence (без санкции — недостаточно данных).
                    raise ValueError("no statutory ceiling")
                category = categorize(guilt, statutory_ceiling)
                check.value = next(key for key, val in _CATEGORIES.items() if val == category)
                check.explanation = (
                    "Предварительная категория по процитированным данным. Проверьте санкцию "
                    "статьи, дату преступления и применимую редакцию закона."
                )
                if cited is text_guilt:
                    check.explanation += " Форма вины взята из текста приговора."
            else:
                if facts is None:
                    raise ValueError("no legal facts")
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
    if (
        extracted_recidivism is not None
        and recidivism_quote
        and recidivism_quote
        in (extracted_source_text if extracted_source_text is not None else source_text)
    ):
        art18 = results[1]
        stated = {
            Recidivism.NONE: "отсутствует",
            Recidivism.SIMPLE: "простой",
            Recidivism.DANGEROUS: "опасный",
            Recidivism.ESPECIALLY_DANGEROUS: "особо опасный",
        }[extracted_recidivism]
        if art18.value is not None and art18.value != extracted_recidivism.value:
            art18.status = "insufficient_data"
            art18.explanation += " Расчёт расходится с указанием рецидива в тексте; нужна сверка."
        elif art18.value is None:
            art18.explanation = (
                "В тексте указан вид рецидива. Это извлечённый факт, а не проверка его "
                "правильности по ст. 18; для расчёта недостаточно сведений о судимостях."
            )
        if art18.value is None or art18.value == extracted_recidivism.value:
            art18.recidivism_input = extracted_recidivism.value
        if art18.value is None:
            art18.value = f"В тексте: {stated}"
        art18.explanation += f" В тексте: {stated}."
        art18.evidence = list(dict.fromkeys([*art18.evidence, recidivism_quote]))
    return results
