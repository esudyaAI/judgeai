"""Human edits of judicial fine-credit statements, without calculating a conversion."""

from dataclasses import asdict, replace

from legal_core.entities import FineCredit, ImposedSentence

_FIELDS = {"scope", "count_index", "original_amount", "reduced_amount", "released", "status"}


def validate_fine_credit(value):
    if type(value) is not dict or set(value) != _FIELDS:
        raise ValueError("invalid_fine_credit")
    if type(value["scope"]) is not str or value["scope"] not in ("count", "final", "unassigned"):
        raise ValueError("invalid_scope")
    index = value["count_index"]
    if value["scope"] == "count":
        if type(index) is not int or index < 0:
            raise ValueError("invalid_count")
    elif index is not None:
        raise ValueError("invalid_count")
    if type(value["released"]) is not bool or value["status"] not in ("stated", "requires_review"):
        raise ValueError("invalid_status")
    for key in ("original_amount", "reduced_amount"):
        amount = value[key]
        if amount is not None and (type(amount) not in (int, float) or not 0 <= amount <= 10**15):
            raise ValueError("invalid_amount")
    original, reduced = value["original_amount"], value["reduced_amount"]
    if original is not None and reduced is not None and reduced > original:
        raise ValueError("invalid_amount")
    if value["released"] and reduced not in (None, 0):
        raise ValueError("contradictory_release")


def fine_credit_catalog(prepared):
    if prepared.sentence is not None:
        for index, credit in enumerate(prepared.sentence.fine_credits):
            value = {name: item for name, item in asdict(credit).items() if name != "quote"}
            yield (
                f"sentence/fine_credit/{index}",
                "Зачёт штрафа по решению суда",
                "fine_credit",
                None if f"fine_credit/{index}" in prepared.unknown_fields else value,
                credit.quote,
                (),
            )
    yield (
        "sentence/fine_credit/new",
        "Добавить решение о зачёте штрафа",
        "fine_credit",
        None,
        "",
        (),
    )


def set_fine_credit(prepared, position, value, quote):
    sentence = prepared.sentence
    unknown = set(prepared.unknown_fields)
    if value is not None:
        validate_fine_credit(value)
        if value["scope"] == "count" and (
            sentence is None or value["count_index"] >= len(sentence.counts)
        ):
            raise ValueError("invalid_count")
    if position == "new":
        if value is None or (sentence is not None and len(sentence.fine_credits) >= 100):
            raise ValueError("invalid_append")
        if sentence is None:
            sentence = ImposedSentence()
            unknown.add("conditional")
        items = (*sentence.fine_credits, FineCredit(**value, quote=quote))
    else:
        if sentence is None:
            raise ValueError("missing_sentence")
        index = int(position)
        items = list(sentence.fine_credits)
        key = f"fine_credit/{index}"
        if value is None:
            unknown.add(key)
        else:
            unknown.discard(key)
            items[index] = FineCredit(**value, quote=quote)
        items = tuple(items)
    return replace(
        prepared,
        sentence=replace(sentence, fine_credits=items),
        unknown_fields=tuple(sorted(unknown)),
    )
