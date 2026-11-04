"""Prepared sentencing data; existing core rules supply the legal arithmetic."""

from dataclasses import dataclass, field

from legal_core.entities import Category, Guilt, ImposedSentence
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import Regime, check_regime

from src.domain.prepared_legal import PreparedFact


@dataclass(frozen=True)
class PreparedRegimeInputs:
    imposed: PreparedFact = field(default_factory=PreparedFact)
    male: PreparedFact = field(default_factory=PreparedFact)
    served_before: PreparedFact = field(default_factory=PreparedFact)
    has_regime_statement: bool = False

    def __post_init__(self):
        if self.imposed.value is not None:
            Regime(self.imposed.value)
        for fact in (self.male, self.served_before):
            if fact.value is not None and type(fact.value) is not bool:
                raise ValueError("Regime flags must be boolean or unknown")


@dataclass(frozen=True)
class PreparedCircumstance:
    name: str
    norm: str
    quote: str
    established: bool | None = True

    def __post_init__(self):
        if self.established is not None and type(self.established) is not bool:
            raise ValueError("Circumstance status must be boolean or unknown")
        if not isinstance(self.norm, str) or not self.norm.strip():
            raise ValueError("A prepared circumstance requires a norm")
        if not isinstance(self.quote, str) or not self.quote.strip():
            raise ValueError("A prepared circumstance requires a quote")


@dataclass(frozen=True)
class PreparedSentencingInputs:
    sentence: ImposedSentence | None
    mitigating: tuple[PreparedCircumstance, ...] = ()
    aggravating: tuple[PreparedCircumstance, ...] = ()
    rejected_circumstances: bool = False
    no_aggravating: PreparedFact = field(default_factory=PreparedFact)
    art64_by_count: tuple[PreparedFact, ...] = ()
    regime: PreparedRegimeInputs = field(default_factory=PreparedRegimeInputs)
    subject_warnings: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    guilt_by_count: tuple[PreparedFact, ...] | None = None
    aggregate_absorption: tuple[bool | None, bool | None] | None = None

    def __post_init__(self):
        if self.aggregate_absorption is not None and (
            len(self.aggregate_absorption) != 2
            or any(v is not None and type(v) is not bool for v in self.aggregate_absorption)
        ):
            raise ValueError("Invalid absorption facts")
        expected = len(self.sentence.counts) if self.sentence is not None else 0
        if self.guilt_by_count is not None and len(self.guilt_by_count) != expected:
            raise ValueError("Prepared guilt does not match sentence counts")
        if len(self.art64_by_count) != expected:
            raise ValueError("Prepared exceptions do not match the sentence counts")
        for fact in (self.no_aggravating, *self.art64_by_count):
            if fact.value is not None and type(fact.value) is not bool:
                raise ValueError("Sentencing flags must be boolean or unknown")


def evaluate_regime_inputs(
    inputs: PreparedRegimeInputs,
    recidivism: Recidivism,
    category: Category | None,
    guilt: Guilt | None,
):
    imposed = Regime(inputs.imposed.value) if inputs.imposed.value is not None else None
    if imposed is None and not inputs.has_regime_statement:
        return None
    return check_regime(
        imposed=imposed,
        guilt=guilt,
        category=category,
        male=inputs.male.value,
        recidivism=recidivism,
        served_imprisonment_before=inputs.served_before.value,
    )
