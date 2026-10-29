"""Operative part of a first-instance verdict -> one block per convicted person.

A verdict on several people convicts each in a paragraph of its own: "А. признать виновным …",
"Признать Б. виновной …". Counts of the same person ("Его же признать виновным", the same
name again) stay in that person's block.
"""

import re

# A paragraph that convicts someone; "невиновным" never matches (no space before "виновн").
_CONVICTION = re.compile(
    r"^[ \t]*(?:(?P<before>[^\n]{1,80}?)\s+признать\s+виновн"
    r"|признать\s+(?P<after>[^\n]{1,80}?)\s+виновн)",
    re.IGNORECASE | re.MULTILINE,
)
_SAME_PERSON = re.compile(r"^(?:его|е[её])\s+же$", re.IGNORECASE)


def _person(match: re.Match) -> str:
    raw = match["before"] or match["after"] or ""
    return re.sub(r"[\s,]+", " ", raw).strip(" ,.").lower()


def split_defendants(operative: str) -> list[str]:
    """Blocks of the operative part in order, one per person; [operative] for a single person."""
    starts: list[int] = []
    people: list[str] = []
    for match in _CONVICTION.finditer(operative):
        person = _person(match)
        if _SAME_PERSON.match(person) or person in people:
            continue
        starts.append(match.start())
        people.append(person)
    if len(starts) < 2:
        return [operative]
    starts[0] = 0  # text before the first conviction belongs to the first person
    return [operative[a:b] for a, b in zip(starts, [*starts[1:], len(operative)], strict=True)]
