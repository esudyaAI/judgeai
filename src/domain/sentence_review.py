"""Typed sentence edits. Core entities and parsers remain the sole legal input model."""

from dataclasses import replace
from datetime import date

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    Unfinished,
)
from legal_core.precedents import FIRST_SPECIAL_PART_ARTICLE, parse_qualifications

from src.domain.fine_credit_review import fine_credit_catalog, set_fine_credit, validate_fine_credit
from src.domain.prepared_legal import CATEGORY_VALUES, PRIOR_FIELD_KINDS, PreparedFact
from src.domain.prepared_sentencing import PreparedCircumstance

_TERMS = ("final", "intermediate", "unserved", "joined", "credited")
_TERM_LABELS = {
    "final": "Окончательное наказание",
    "intermediate": "Промежуточное наказание",
    "unserved": "Неотбытая часть",
    "joined": "Присоединённая часть",
    "credited": "Зачтённое наказание",
}


def term_value(term):
    return (
        {
            "kind": term.kind.value,
            "amount": term.amount,
            "unit": term.unit.value if term.unit else None,
        }
        if term
        else None
    )


def read_term(value):
    if type(value) is not dict or set(value) != {"kind", "amount", "unit"}:
        raise ValueError("invalid_term")
    kind = PunishmentKind(value["kind"])
    amount, unit = value["amount"], value["unit"]
    if amount is None and unit is None:
        return PunishmentTerm(kind)
    if kind in (PunishmentKind.LIFE_IMPRISONMENT, PunishmentKind.DEATH_PENALTY):
        raise ValueError("invalid_term")
    if type(amount) not in (int, float) or not 0 < amount <= 10**15:
        raise ValueError("invalid_amount")
    unit = MeasureUnit(unit)
    allowed = (
        (MeasureUnit.RUBLES,)
        if kind is PunishmentKind.FINE
        else (MeasureUnit.HOURS,)
        if kind is PunishmentKind.COMPULSORY_WORKS
        else (MeasureUnit.MONTHS, MeasureUnit.DAYS)
    )
    if unit not in allowed:
        raise ValueError("invalid_unit")
    return PunishmentTerm(kind, amount, unit)


def read_qualification(value):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise ValueError("invalid_qualification")
    found = parse_qualifications(value)
    if len(found) != 1 or int(found[0].article.split(".")[0]) < FIRST_SPECIAL_PART_ARTICLE:
        raise ValueError("invalid_qualification")
    qualification = found[0]
    return ArticleReference(qualification.article, qualification.part)


def read_date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("invalid_date")
    return date.fromisoformat(value)


def validate_sentence_value(kind, value):
    if kind == "fine_credit":
        validate_fine_credit(value)
    elif kind == "term":
        read_term(value)
    elif kind == "qualification":
        read_qualification(value)
    elif kind == "date":
        read_date(value)
    elif kind == "positive_integer":
        if type(value) is not int or not 0 < value <= 120000:
            raise ValueError("invalid_integer")
    elif kind == "stage":
        if type(value) is not str or value not in ("completed", "attempt", "preparation"):
            raise ValueError("invalid_stage")
    elif kind == "circumstance":
        if (
            type(value) is not dict
            or set(value) != {"name", "norm", "established"}
            or type(value["established"]) is not bool
        ):
            raise ValueError("invalid_circumstance")
        if any(
            type(value[name]) is not str or not value[name].strip() or len(value[name]) > 1000
            for name in ("name", "norm")
        ):
            raise ValueError("invalid_circumstance")
    elif kind == "prior":
        if type(value) is not dict or not value or set(value) - dict(PRIOR_FIELD_KINDS).keys():
            raise ValueError("invalid_prior")
        for name, item in value.items():
            expected = dict(PRIOR_FIELD_KINDS)[name]
            if item is not None and (
                type(item) is not expected
                or (expected is str and (not item.strip() or len(item) > 256))
            ):
                raise ValueError("invalid_prior")
            if name == "guilt" and item not in (None, "intentional", "negligent"):
                raise ValueError("invalid_prior")
            if name == "category" and item is not None and item not in CATEGORY_VALUES:
                raise ValueError("invalid_prior")
        if not value.get("judgment_id"):
            raise ValueError("missing_judgment_id")
    elif kind == "count":
        if (
            type(value) is not dict
            or not {"qualification", "main"} <= set(value)
            or set(value) - {"qualification", "main", "additional", "stage", "offence_date"}
        ):
            raise ValueError("invalid_count")
        read_qualification(value["qualification"])
        read_term(value["main"])
        extra = value.get("additional", [])
        if type(extra) is not list or len(extra) > 20:
            raise ValueError("invalid_additional")
        for term in extra:
            read_term(term)
        if value.get("stage") is not None:
            validate_sentence_value("stage", value["stage"])
        if value.get("offence_date") is not None:
            read_date(value["offence_date"])
    else:
        return False
    return True


def sentence_catalog(prepared):
    """Yield a finite field catalog. /new is an append command, never an arbitrary index."""
    sentence = prepared.sentence
    yield from fine_credit_catalog(prepared)
    for group in ("mitigating", "aggravating"):
        for index, item in enumerate(getattr(prepared, group)):
            yield (
                f"circumstance/{group}/{index}",
                "Смягчающее обстоятельство"
                if group == "mitigating"
                else "Отягчающее обстоятельство",
                "circumstance",
                {"name": item.name, "norm": item.norm, "established": item.established}
                if item.established is not None
                else None,
                item.quote,
                (),
            )
        yield (f"circumstance/{group}/new", "Добавить обстоятельство", "circumstance", None, "", ())
    yield ("sentence/count/new", "Добавить эпизод", "count", None, "", ())
    if sentence is None:
        return
    unknown = set(prepared.unknown_fields)
    if prepared.aggregate_absorption is not None:
        for index, name in enumerate(("intermediate", "final")):
            yield (
                f"sentence/absorption/{name}",
                "Поглощение наказаний",
                "boolean",
                prepared.aggregate_absorption[index],
                sentence.intermediate_quote if index == 0 else sentence.final_quote,
                (),
            )
    for field in _TERMS:
        yield (
            f"sentence/{field}",
            _TERM_LABELS[field],
            "term",
            None if field in unknown else term_value(getattr(sentence, field)),
            getattr(sentence, f"{field}_quote"),
            (),
        )
    for field, label, kind in (
        ("conditional", "Условное осуждение", "boolean"),
        ("probation_months", "Испытательный срок, месяцы", "positive_integer"),
        ("prior_judgment_date", "Дата прежнего приговора", "date"),
        ("aggregation_rule", "Правило совокупности", "text"),
        ("intermediate_rule", "Правило промежуточного итога", "text"),
    ):
        value = getattr(sentence, field)
        if isinstance(value, date):
            value = value.isoformat()
        yield (
            f"sentence/{field}",
            label,
            kind,
            None if field in unknown else value,
            sentence.final_quote,
            (),
        )
    for index, count in enumerate(sentence.counts):
        prefix = f"count/{index}"
        for field, label, kind, value in (
            ("main", "Основное наказание эпизода", "term", term_value(count.main)),
            (
                "qualification",
                "Квалификация эпизода",
                "qualification",
                count.qualification if count.reference else None,
            ),
            (
                "stage",
                "Стадия преступления",
                "stage",
                None
                if count.stage_conflict
                else count.unfinished.value
                if count.unfinished
                else "completed",
            ),
            (
                "offence_date",
                "Дата преступления",
                "date",
                count.offence_date.isoformat() if count.offence_date else None,
            ),
        ):
            yield (
                f"sentence/{prefix}/{field}",
                label,
                kind,
                None if f"{prefix}/{field}" in unknown else value,
                count.offence_date_quote if field == "offence_date" else count.quote,
                (),
            )
        if prepared.guilt_by_count is not None:
            fact = prepared.guilt_by_count[index]
            yield (
                f"sentence/{prefix}/guilt",
                "Форма вины эпизода для совокупности",
                "choice",
                fact.value,
                fact.quote,
                ("intentional", "negligent"),
            )
        for extra, term in enumerate(count.additional):
            path = f"{prefix}/additional/{extra}"
            yield (
                f"sentence/{path}",
                "Дополнительное наказание эпизода",
                "term",
                None if path in unknown else term_value(term),
                count.quote,
                (),
            )
        yield (
            f"sentence/{prefix}/additional/new",
            "Добавить дополнительное наказание эпизода",
            "term",
            None,
            "",
            (),
        )
    for index, term in enumerate(sentence.final_additional):
        path = f"final_additional/{index}"
        yield (
            f"sentence/{path}",
            "Окончательное дополнительное наказание",
            "term",
            None if path in unknown else term_value(term),
            sentence.final_quote,
            (),
        )
    yield (
        "sentence/final_additional/new",
        "Добавить окончательное дополнительное наказание",
        "term",
        None,
        "",
        (),
    )


def set_sentence_fact(prepared, path, value, quote):
    sentence = prepared.sentence
    unknown = set(prepared.unknown_fields)
    if path[0] == "circumstance":
        group, position = path[1:]
        items = list(getattr(prepared, group))
        if position == "new":
            if value is None or len(items) >= 100:
                raise ValueError("invalid_append")
            items.append(PreparedCircumstance(**value, quote=quote))
        else:
            index = int(position)
            items[index] = (
                replace(items[index], established=None)
                if value is None
                else PreparedCircumstance(**value, quote=quote)
            )
        changes = {group: tuple(items)}
        if group == "aggravating" and any(item.established is not False for item in items):
            changes["no_aggravating"] = PreparedFact()
        return replace(prepared, **changes)
    path = path[1:]
    key = "/".join(path)
    if path[0] == "fine_credit":
        return set_fine_credit(prepared, path[1], value, quote)
    if path[0] == "absorption":
        values = list(prepared.aggregate_absorption)
        values[0 if path[1] == "intermediate" else 1] = value
        return replace(prepared, aggregate_absorption=tuple(values))
    if path == ["count", "new"]:
        if value is None or (sentence is not None and len(sentence.counts) >= 100):
            raise ValueError("invalid_append")
        if sentence is None:
            sentence = ImposedSentence()
            unknown.add("conditional")
            prepared = replace(prepared, aggregate_absorption=(None, None))
        elif not sentence.counts and sentence.final is None and not sentence.final_quote:
            unknown.add("conditional")
            prepared = replace(prepared, aggregate_absorption=(None, None))
        stage = value.get("stage")
        count = CountSentence(
            value["qualification"],
            read_qualification(value["qualification"]),
            read_term(value["main"]),
            tuple(read_term(t) for t in value.get("additional", [])),
            quote,
            Unfinished(stage) if stage and stage != "completed" else None,
            stage is None,
            read_date(value["offence_date"]) if value.get("offence_date") else None,
            quote if value.get("offence_date") else "",
        )
        sentence = replace(sentence, counts=(*sentence.counts, count))
        guilt = prepared.guilt_by_count
        if guilt is None:
            guilt = tuple(PreparedFact() for _ in range(len(sentence.counts) - 1))
        return replace(
            prepared,
            sentence=sentence,
            art64_by_count=(*prepared.art64_by_count, PreparedFact()),
            guilt_by_count=(*guilt, PreparedFact()) if guilt is not None else None,
            unknown_fields=tuple(sorted(unknown)),
        )
    if sentence is None:
        raise ValueError("missing_sentence")
    if value is None:
        unknown.add(key)
    else:
        unknown.discard(key)
    if path[0] == "count":
        index, field = int(path[1]), path[2]
        rows = list(sentence.counts)
        count = rows[index]
        if field == "guilt":
            guilt = list(prepared.guilt_by_count)
            guilt[index] = PreparedFact(value, quote)
            return replace(prepared, guilt_by_count=tuple(guilt))
        if field == "main":
            count = replace(
                count, main=read_term(value) if value is not None else count.main, quote=quote
            )
        elif field == "additional":
            extra = list(count.additional)
            if path[3] == "new":
                if value is None or len(extra) >= 20:
                    raise ValueError("invalid_append")
                extra.append(read_term(value))
            elif value is not None:
                extra[int(path[3])] = read_term(value)
            count = replace(count, additional=tuple(extra), quote=quote)
        elif field == "qualification":
            count = replace(
                count,
                qualification=value or "Квалификация не установлена",
                reference=read_qualification(value) if value is not None else None,
                quote=quote,
            )
        elif field == "stage":
            count = replace(
                count,
                unfinished=Unfinished(value) if value not in (None, "completed") else None,
                stage_conflict=value is None,
                quote=quote,
            )
        elif field == "offence_date":
            if (read_date(value) if value is not None else None) != count.offence_date:
                unknown.add(f"statute/{index}")
            count = replace(
                count,
                offence_date=read_date(value) if value is not None else None,
                offence_date_quote=quote,
            )
        rows[index] = count
        sentence = replace(sentence, counts=tuple(rows))
    elif path[0] == "final_additional":
        extra = list(sentence.final_additional)
        if path[1] == "new":
            if value is None or len(extra) >= 20:
                raise ValueError("invalid_append")
            extra.append(read_term(value))
        elif value is not None:
            extra[int(path[1])] = read_term(value)
        sentence = replace(sentence, final_additional=tuple(extra), final_quote=quote)
    elif path[0] in _TERMS:
        sentence = replace(
            sentence,
            **{path[0]: read_term(value) if value is not None else None, f"{path[0]}_quote": quote},
        )
    elif path[0] == "conditional":
        sentence = replace(
            sentence,
            conditional=value if value is not None else sentence.conditional,
            final_quote=quote,
        )
    elif path[0] == "prior_judgment_date":
        sentence = replace(
            sentence,
            prior_judgment_date=read_date(value) if value is not None else None,
            prior_judgment_quote=quote,
        )
    else:
        sentence = replace(sentence, **{path[0]: value}, final_quote=quote)
    return replace(prepared, sentence=sentence, unknown_fields=tuple(sorted(unknown)))
