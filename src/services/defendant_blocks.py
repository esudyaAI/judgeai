"""Operative part of a first-instance verdict -> one block per convicted person.

A verdict on several people convicts each in a paragraph of its own: "А. признать виновным …",
"Признать Б. виновной …". Counts of the same person ("Его же признать виновным", the same
name again) stay in that person's block.
"""

import re

_WRAPPED_IDENTITY = (
    r"(?:ФИО\d+(?:-[А-ЯЁ.]+)?|[А-ЯЁ]\.[ \t]*[А-ЯЁ]\.[ \t]*[А-ЯЁ]\."
    r"|[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ]\.[ \t]*[А-ЯЁ]\."
    r"|[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ][а-яё-]+)"
)
# A paragraph that convicts someone; "невиновным" never matches (no space before "виновн").
_CONVICTION = re.compile(
    r"^[ \t]*(?:признать[ \t]+виновн[а-яё]*[ \t]+"
    r"(?P<after_verdict>[^\n]{1,80}?)(?=[ \t]+(?:в[ \t]+совершении|виновн))"
    r"|(?P<wrapped>" + _WRAPPED_IDENTITY + r")[ \t]*\n[ \t]*признать[ \t]+виновн"
    r"|(?P<before>[^\n]{1,80}?)[ \t]+признать[ \t]+виновн"
    r"|признать[ \t]+(?P<after>[^\n]{1,80}?)[ \t]+виновн)",
    re.IGNORECASE | re.MULTILINE,
)

_SAME_PERSON = re.compile(r"^(?:его|е[её])\s+же$", re.IGNORECASE)


def _person(match: re.Match) -> str:
    raw = match["after_verdict"] or match["wrapped"] or match["before"] or match["after"] or ""
    return re.sub(r"[\s,]+", " ", raw).strip(" ,.").lower()


def _operative_spans(operative: str):
    """Unmodified ranges grouped in the same order as the convicted people."""
    matches = list(_CONVICTION.finditer(operative))
    people = []
    chunks = {}
    current = None
    for index, match in enumerate(matches):
        person = _person(match)
        if not _SAME_PERSON.match(person):
            current = person
        if current is None:
            continue
        if current not in people:
            people.append(current)
            chunks[current] = []
        start = 0 if index == 0 else match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(operative)
        chunks[current].append((start, end))
    return people, chunks


def split_defendants(operative: str) -> list[str]:
    people, chunks = _operative_spans(operative)
    return (
        ["".join(operative[start:end] for start, end in chunks[person]) for person in people]
        if len(people) > 1
        else [operative]
    )


def defendant_names(operative: str) -> list[str]:
    people = []
    for match in _CONVICTION.finditer(operative):
        raw = _person(match)
        if _SAME_PERSON.match(raw):
            continue
        for person in re.split(r"\s+и\s+", raw):
            if person not in people:
                people.append(person)
    return people


def _mentioned(statement: str, people: list[str]) -> set[str]:
    owners = set()
    for name in people:
        first = name.split()[0]
        stem = (
            first
            if re.fullmatch(r"фио\d+|[а-яё]", first, re.I)
            else first[:-2]
            if len(first) > 6
            else first
        )
        if re.search(rf"(?<![а-яё\d]){re.escape(stem)}[а-яё]*(?![а-яё\d])", statement, re.I):
            owners.add(name)
    return owners


def _scope_person_spans(text: str, person: str, people: list[str], *, common=False):
    from src.infrastructure.circumstance_extractor import circumstance_statements

    ranges, cursor = [], 0
    for statement in circumstance_statements(text):
        start = text.find(statement, cursor)
        if start < 0:
            raise ValueError("Cannot locate original subject statement")
        end = start + len(statement)
        cursor = end
        owners = _mentioned(statement, people)
        explicit_common = common and re.search(
            r"\b(?:обоим|всем|каждому)\s+(?:подсудим|осужд[её]нн)\w*", statement, re.I
        )
        if owners == {person} or (not owners and explicit_common):
            ranges.append((start, end))
    return tuple(ranges)


def scope_person_text(text: str, person: str, people: list[str], *, common: bool = False) -> str:
    """Same conservative attribution, retaining exact original spans for review binding."""
    return "\n\n".join(
        text[start:end] for start, end in _scope_person_spans(text, person, people, common=common)
    )


def defendant_source_spans(text: str):
    """Original-coordinate ranges for exactly the subjects used by scoped_verdicts."""
    from src.services.verdict_segmenter import segment_verdict

    parts = segment_verdict(text)
    names = defendant_names(parts.operative)
    if len(names) < 2:
        return []
    intro_start = text.find(parts.introduction) if parts.introduction else 0
    after_intro = intro_start + len(parts.introduction)
    description_start = (
        text.find(parts.description, after_intro) if parts.description else after_intro
    )
    operative_start = text.rfind(parts.operative) if parts.operative else len(text)
    if min(intro_start, description_start, operative_start) < 0:
        raise ValueError("Cannot locate original verdict sections")
    operative_people, blocks = _operative_spans(parts.operative)
    first_conviction = next(_CONVICTION.finditer(parts.operative), None)
    prefix_end = first_conviction.start() if first_conviction else 0
    result = []
    for index, person in enumerate(names):
        ranges = [
            (intro_start + start, intro_start + end)
            for start, end in _scope_person_spans(parts.introduction, person, names)
        ]
        ranges += [
            (description_start + start, description_start + end)
            for start, end in _scope_person_spans(parts.description, person, names, common=True)
        ]
        ranges += [
            (operative_start + start, operative_start + end)
            for start, end in _scope_person_spans(
                parts.operative[:prefix_end], person, names, common=True
            )
        ]
        if len(operative_people) == len(names):
            ranges += [
                (operative_start + start, operative_start + end)
                for start, end in (
                    (max(start, prefix_end), end) for start, end in blocks[operative_people[index]]
                )
            ]
        result.append((person, tuple(ranges)))
    return result


def scoped_verdicts(text: str) -> list[tuple[str, str]]:
    """Return separate verdict texts when the operative part identifies several people."""
    from src.services.verdict_segmenter import segment_verdict

    parts = segment_verdict(text)
    people = defendant_names(parts.operative)
    blocks = split_defendants(parts.operative)
    if len(people) < 2:
        return []
    if len(blocks) != len(people):
        # Collective conviction without individual punishment attribution: retain unknowns.
        blocks = ["" for _ in people]
    return [
        (
            person,
            "\n".join(
                [
                    scope_person_text(parts.introduction, person, people),
                    "УСТАНОВИЛ:",
                    scope_person_text(parts.description, person, people, common=True),
                    "ПРИГОВОРИЛ:",
                    block,
                ]
            ),
        )
        for person, block in zip(people, blocks, strict=True)
    ]
