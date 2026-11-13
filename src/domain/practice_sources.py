"""T45.2 — the sources of a practice answer, written by code under the answer.

Every verdict counted for the answer is a source: court, date, УИД, its own term and the link
to the published text. The list is part of the answer the user reads in the chat, so it is
written here and never by a model; only the first ``limit`` verdicts are listed, newest first,
and the rest is stated as a number, not hidden.
"""

from datetime import date

from src.domain.practice_facts import CountedVerdict, PracticeTermFacts, format_months

SOURCES_SHOWN = 10


def _order(verdict: CountedVerdict) -> tuple[bool, date, int]:
    # Newest first; verdicts without a date go last, ties keep the card order stable.
    day = verdict.decision_date
    return (day is None, -(day or date.min).toordinal(), verdict.card_id)


def _source_line(number: int, verdict: CountedVerdict) -> str:
    parts = [verdict.court_name or "суд не указан"]
    if verdict.decision_date is not None:
        parts.append(verdict.decision_date.strftime("%d.%m.%Y"))
    if verdict.uid:
        parts.append(f"УИД {verdict.uid}")
    if verdict.months is not None:
        term = format_months(verdict.months)
        parts.append(f"{term} условно" if verdict.conditional else term)
    else:
        parts.append("срок лишения свободы не назначен или не распознан")
    if verdict.source_url:
        parts.append(verdict.source_url)
    return f"{number}. " + ", ".join(parts)


def describe_practice_sources(facts: PracticeTermFacts, limit: int = SOURCES_SHOWN) -> str:
    """«Источники: …» — empty when no verdict was counted."""
    if not facts.counted:
        return ""
    ordered = sorted(facts.counted, key=_order)
    lines = ["Источники (приговоры, по которым посчитаны цифры):"]
    lines += [_source_line(i, v) for i, v in enumerate(ordered[:limit], start=1)]
    rest = len(ordered) - limit
    if rest > 0:
        lines.append(f"…и ещё {rest} учтено в расчёте, в список не вошли.")
    return "\n".join(lines)
