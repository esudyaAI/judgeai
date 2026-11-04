"""Allowlisted decisions over prepared rule inputs; no output-JSON patching."""

from dataclasses import asdict, dataclass, replace

from legal_core.entities import Guilt
from legal_core.precedents import Recidivism
from legal_core.rules.art58 import Regime

from src.domain.prepared_legal import CATEGORY_VALUES, PRIOR_FIELD_KINDS, PreparedFact
from src.domain.review_evidence import Evidence, validate_evidence
from src.domain.sentence_review import sentence_catalog, set_sentence_fact, validate_sentence_value


class InvalidReview(ValueError):
    pass


class ReviewConflict(ValueError):
    pass


@dataclass(frozen=True)
class FactSpec:
    id: str
    subject_index: int
    label: str
    kind: str
    value: object
    quote: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactDecision:
    fact_id: str
    operation: str
    reason: str
    value: object = None
    evidence: Evidence | None = None


_LEGAL = (
    ("guilt", "Форма вины", "choice", tuple(g.value for g in Guilt)),
    ("category", "Категория текущего преступления", "choice", tuple(CATEGORY_VALUES)),
    ("real_imprisonment", "Реальное лишение свободы", "boolean", ()),
    ("history_complete", "Полнота сведений о судимостях", "boolean", ()),
)
_REGIME = (
    (
        "imposed",
        "Назначенный вид исправительного учреждения",
        "choice",
        tuple(r.value for r in Regime),
    ),
    ("male", "Мужской пол", "boolean", ()),
    ("served_before", "Прежнее отбывание лишения свободы", "boolean", ()),
)
PRIOR_LABELS = {
    "judgment_id": "Идентификатор прежнего приговора",
    "guilt": "Форма вины по прежнему приговору",
    "category": "Категория прежнего преступления",
    "real_imprisonment": "Реальное лишение свободы по прежнему приговору",
    "adult_at_offence": "Совершеннолетие на дату прежнего преступления",
    "active_at_offence": "Судимость действовала на дату преступления",
    "convicted_before_offence": "Осуждение до текущего преступления",
    "imprisoned_by_sentence": "Лишение свободы по прежнему приговору",
    "conditional_or_deferred": "Условное осуждение или отсрочка",
    "revoked_and_sent_before_offence": "Отмена и направление для отбывания до преступления",
}


def _spec(subject, path, label, kind, fact, choices=()):
    return FactSpec(
        f"subject/{subject}/{path}", subject, label, kind, fact.value, fact.quote, choices
    )


def review_catalog(legal, sentencing):
    if set(legal) != set(sentencing):
        raise InvalidReview("invalid_subjects")
    result = []
    for subject, inputs in sorted(legal.items()):
        for name, label, kind, choices in _LEGAL:
            fact = (
                (
                    inputs.model_guilt
                    if inputs.model_guilt.value is not None
                    else inputs.category_guilt
                )
                if name == "guilt"
                else getattr(inputs, name)
            )
            result.append(_spec(subject, f"legal/{name}", label, kind, fact, choices))
        result.append(
            _spec(
                subject,
                "legal/stated_recidivism",
                "Указанный в приговоре рецидив",
                "choice",
                PreparedFact(inputs.stated_recidivism.value, inputs.stated_quote)
                if inputs.stated_recidivism is not None and inputs.stated_quote
                else PreparedFact(),
                tuple(r.value for r in Recidivism),
            )
        )
        for index, row in enumerate(inputs.prior_convictions):
            prior = dict(row)
            for name, kind in PRIOR_FIELD_KINDS:
                choices = (
                    tuple(g.value for g in Guilt)
                    if name == "guilt"
                    else (tuple(CATEGORY_VALUES) if name == "category" else ())
                )
                result.append(
                    _spec(
                        subject,
                        f"prior/{index}/{name}",
                        PRIOR_LABELS.get(name, name),
                        "boolean" if kind is bool else "choice" if choices else "text",
                        prior.get(name, PreparedFact()),
                        choices,
                    )
                )
        result.append(
            FactSpec(
                f"subject/{subject}/prior/new",
                subject,
                "Добавить прежний приговор",
                "prior",
                None,
                "",
            )
        )
        prepared = sentencing[subject]
        for path, label, kind, value, quote, choices in sentence_catalog(prepared):
            result.append(
                FactSpec(f"subject/{subject}/{path}", subject, label, kind, value, quote, choices)
            )
        result.append(
            _spec(
                subject,
                "sentencing/no_aggravating",
                "Отсутствие отягчающих обстоятельств",
                "boolean",
                prepared.no_aggravating,
            )
        )
        for index, fact in enumerate(prepared.art64_by_count):
            result.append(
                _spec(
                    subject,
                    f"sentencing/count/{index}/art64",
                    "Применение ст. 64 к эпизоду",
                    "boolean",
                    fact,
                )
            )
        for name, label, kind, choices in _REGIME:
            result.append(
                _spec(
                    subject, f"regime/{name}", label, kind, getattr(prepared.regime, name), choices
                )
            )
    return tuple(result)


def _check_value(spec, value):
    try:
        if validate_sentence_value(spec.kind, value):
            return
    except (ValueError, TypeError, KeyError):
        raise InvalidReview("invalid_value") from None
    if spec.kind == "boolean" and type(value) is bool:
        return
    if spec.kind == "choice" and type(value) is str and value in spec.choices:
        return
    if spec.kind == "text" and type(value) is str and value.strip() and len(value) <= 256:
        return
    raise InvalidReview("invalid_value")


def _set_fact(legal, sentencing, spec, fact):
    # The path comes from our catalog, never from an arbitrary client JSON path.
    path = spec.id.split("/")[2:]
    subject = spec.subject_index
    if path[0] == "legal":
        field = path[1]
        if field == "guilt":
            legal[subject] = replace(
                legal[subject], model_guilt=fact, category_guilt=fact, category_uses_text=False
            )
            if sentencing[subject].guilt_by_count is not None:
                sentencing[subject] = replace(
                    sentencing[subject],
                    guilt_by_count=tuple(fact for _ in sentencing[subject].guilt_by_count),
                )
        elif field == "stated_recidivism":
            legal[subject] = replace(
                legal[subject],
                stated_recidivism=Recidivism(fact.value) if fact.value is not None else None,
                stated_quote=fact.quote,
            )
        else:
            legal[subject] = replace(legal[subject], **{field: fact})
    elif path[0] == "prior":
        rows = list(legal[subject].prior_convictions)
        index, field = int(path[1]), path[2]
        row = dict(rows[index])
        row[field] = fact
        rows[index] = tuple(row.items())
        legal[subject] = replace(legal[subject], prior_convictions=tuple(rows))
    elif path[0] == "regime":
        regime = replace(sentencing[subject].regime, **{path[1]: fact})
        if path[1] == "imposed":
            regime = replace(regime, has_regime_statement=True)
        sentencing[subject] = replace(sentencing[subject], regime=regime)
    elif path[1] == "no_aggravating":
        sentencing[subject] = replace(sentencing[subject], no_aggravating=fact)
    else:
        flags = list(sentencing[subject].art64_by_count)
        flags[int(path[2])] = fact
        sentencing[subject] = replace(sentencing[subject], art64_by_count=tuple(flags))


def apply_decisions(legal, sentencing, documents, context, decisions):
    if not 1 <= len(decisions) <= 200:
        raise InvalidReview("invalid_decisions")
    specs = {spec.id: spec for spec in review_catalog(legal, sentencing)}
    original_legal = legal
    original_sentencing = sentencing
    legal, sentencing = dict(legal), dict(sentencing)
    seen, audit, changed = set(), [], False
    for decision in decisions:
        spec = specs.get(decision.fact_id)
        if spec is None or decision.fact_id in seen:
            raise InvalidReview("invalid_fact")
        seen.add(decision.fact_id)
        if (
            type(decision.reason) is not str
            or not decision.reason.strip()
            or len(decision.reason) > 2000
        ):
            raise InvalidReview("invalid_reason")
        if decision.operation == "unknown":
            if decision.value is not None or decision.evidence is not None:
                raise InvalidReview("unknown_with_value")
            value, quote = None, ""
        elif decision.operation in ("confirm", "correct"):
            if decision.operation == "confirm":
                if decision.value is not None or spec.value is None:
                    raise InvalidReview("invalid_confirmation")
                value = spec.value
            else:
                value = decision.value
            _check_value(spec, value)
            if decision.evidence is None:
                raise InvalidReview("missing_evidence")
            validate_evidence(documents, context, spec.subject_index, decision.evidence)
            quote = decision.evidence.quote
        else:
            raise InvalidReview("invalid_operation")
        path = spec.id.split("/")[2:]
        try:
            if path[0] in ("sentence", "circumstance"):
                sentencing[spec.subject_index] = set_sentence_fact(
                    sentencing[spec.subject_index], path, value, quote
                )
            elif path == ["prior", "new"]:
                if value is None or len(legal[spec.subject_index].prior_convictions) >= 100:
                    raise ValueError("invalid_append")
                row = tuple(
                    (
                        name,
                        PreparedFact(value.get(name), quote if value.get(name) is not None else ""),
                    )
                    for name, _ in PRIOR_FIELD_KINDS
                )
                legal[spec.subject_index] = replace(
                    legal[spec.subject_index],
                    prior_convictions=(*legal[spec.subject_index].prior_convictions, row),
                )
            else:
                _set_fact(legal, sentencing, spec, PreparedFact(value, quote))
        except (ValueError, TypeError, KeyError, IndexError):
            raise InvalidReview("invalid_value") from None
        changed |= type(value) is not type(spec.value) or value != spec.value
        if spec.id.endswith("/legal/guilt"):
            # Selecting text guilt for display does not make a missing model input known.
            before = original_legal[spec.subject_index]
            changed |= before.model_guilt.value != value or before.category_guilt.value != value
            original_scopes = original_sentencing[spec.subject_index]
            changed |= original_scopes.guilt_by_count is not None and any(
                f.value != value for f in original_scopes.guilt_by_count
            )
        audit.append(
            {
                **asdict(decision),
                "subject_index": spec.subject_index,
                "field_label": spec.label,
                "old_value": spec.value,
                "new_value": value,
            }
        )
    return legal, sentencing, tuple(audit), changed
