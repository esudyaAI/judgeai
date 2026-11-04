"""Quoted inputs and evaluation through existing core rules, without parsing or frameworks."""

from dataclasses import dataclass, field

from legal_core.entities import Category, Guilt, SanctionCeiling
from legal_core.precedents import Recidivism
from legal_core.rules.art15 import categorize
from legal_core.rules.art18 import CurrentOffence, PriorConviction, classify_recidivism

CATEGORY_VALUES = {
    "small": Category.SMALL,
    "medium": Category.MEDIUM,
    "grave": Category.GRAVE,
    "especially_grave": Category.ESPECIALLY_GRAVE,
}
PRIOR_FIELD_KINDS = tuple(
    (name, str if name in ("judgment_id", "guilt", "category") else bool)
    for name in PriorConviction.__dataclass_fields__
)


@dataclass(frozen=True)
class PreparedFact:
    # Keep the raw primitive uncoerced when decoded: 1 is not a confirmed True.
    value: object = None
    quote: str = ""

    def __post_init__(self):
        if type(self.value) not in (str, bool, type(None)):
            raise ValueError("Unsupported prepared fact type")
        if not isinstance(self.quote, str) or (self.value is not None and not self.quote.strip()):
            raise ValueError("A known fact requires a quote")


@dataclass(frozen=True)
class PreparedLegalInputs:
    model_guilt: PreparedFact = field(default_factory=PreparedFact)
    category_guilt: PreparedFact = field(default_factory=PreparedFact)
    category_uses_text: bool = False
    category: PreparedFact = field(default_factory=PreparedFact)
    real_imprisonment: PreparedFact = field(default_factory=PreparedFact)
    history_complete: PreparedFact = field(default_factory=PreparedFact)
    prior_convictions: tuple[tuple[tuple[str, PreparedFact], ...], ...] = ()
    stated_recidivism: Recidivism | None = None
    stated_quote: str = ""


@dataclass(frozen=True)
class LegalEvaluation:
    category: str | None
    category_evidence: tuple[str, ...]
    recidivism: str | None
    recidivism_evidence: tuple[str, ...]
    stated_recidivism: Recidivism | None
    recidivism_input: str | None
    recidivism_conflict: bool


def _required(fact: PreparedFact, kind: type):
    if type(fact.value) is not kind or not fact.quote:
        raise ValueError("Missing prepared fact")
    return fact.value


def evaluate_legal_inputs(inputs: PreparedLegalInputs, ceiling: SanctionCeiling | None = None):
    category, recidivism, category_quotes, prior_quotes = None, None, (), ()
    try:
        if ceiling is None:
            raise ValueError("Missing statutory ceiling")
        result = categorize(Guilt(_required(inputs.category_guilt, str)), ceiling)
        category = next(name for name, value in CATEGORY_VALUES.items() if value == result)
        category_quotes = (inputs.category_guilt.quote,)
    except (ValueError, KeyError):
        pass
    try:
        guilt = Guilt(_required(inputs.model_guilt, str))
        current_category = CATEGORY_VALUES[_required(inputs.category, str)]
        real = _required(inputs.real_imprisonment, bool)
        complete = _required(inputs.history_complete, bool)
        if not complete:
            raise ValueError("Incomplete history")
        quotes = [
            inputs.model_guilt.quote,
            inputs.category.quote,
            inputs.real_imprisonment.quote,
            inputs.history_complete.quote,
        ]
        priors = []
        for fields in inputs.prior_convictions:
            row = dict(fields)
            values = {}
            for name, kind in PRIOR_FIELD_KINDS:
                values[name] = _required(row.get(name, PreparedFact()), kind)
                quotes.append(row[name].quote)
            values["guilt"] = Guilt(values["guilt"])
            values["category"] = CATEGORY_VALUES[values["category"]]
            priors.append(PriorConviction(**values))
        recidivism = classify_recidivism(
            CurrentOffence(guilt, current_category, real), priors, history_complete=complete
        ).value
        prior_quotes = tuple(dict.fromkeys(quotes))
    except (ValueError, KeyError):
        pass
    stated = inputs.stated_recidivism if inputs.stated_quote else None
    conflict = stated is not None and recidivism is not None and recidivism != stated.value
    recidivism_input = stated.value if stated is not None and not conflict else None
    if stated is not None:
        prior_quotes = tuple(dict.fromkeys((*prior_quotes, inputs.stated_quote)))
    return LegalEvaluation(
        category, category_quotes, recidivism, prior_quotes, stated, recidivism_input, conflict
    )
