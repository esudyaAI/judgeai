"""Domain of the sudact.ru crawler: one downloaded court act and its identity.

Pure stdlib: no HTTP, no HTML, no database. The infrastructure layer turns raw
bytes into these values; deduplication and "is this a first-instance verdict"
live here so every caller shares the same rules.
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import date

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

VERDICT_KIND = "приговор"

# Act kinds worth keeping in the practice base; everything else is crawled
# (politeness) but not stored. The kind comes from the sudact page title.
KEEP_KINDS = frozenset({VERDICT_KIND})

_CASE_NUMBER = re.compile(r"№\s*([0-9]{1,2}-[0-9]+/[0-9]{4})")
_UID = re.compile(r"\bУИД\s*№?\s*([0-9]{2}[A-Z]{2}[0-9A-Z-]{10,40})")
_TITLE_DATE = re.compile(r"от\s+(\d{1,2})\s+([а-яё]+)\s+(\d{4})")
_ACT_KIND = re.compile(r"^\s*([А-ЯЁ][а-яё]*(?:\s+[а-яё]+)*)\s*№")
_ARTICLE = re.compile(r"ст\.\s*(\d{1,3}(?:\.\d+)?)(?:\s+ч\.\s*(\d+))?")


@dataclass(frozen=True)
class SudactDocument:
    """A normalized sudact.ru document page with provenance."""

    url: str
    fetched_at: str
    html_sha256: str
    title: str
    act_kind: str
    category: str | None = None
    case_number: str | None = None
    uid: str | None = None
    court_name: str | None = None
    region: str | None = None
    decision_date: str | None = None
    text: str = ""
    text_sha256: str = ""
    articles: list[str] = field(default_factory=list)

    @property
    def is_verdict(self) -> bool:
        return self.act_kind == VERDICT_KIND

    @property
    def dedup_key(self) -> str:
        """UID of the case when known, otherwise the hash of the act text."""
        return f"uid:{self.uid}" if self.uid else f"sha:{self.text_sha256}"

    def to_record(self) -> dict:
        return asdict(self)


def normalize_act_kind(title: str) -> str | None:
    """First words of a sudact title before the case number, lowercased.

    "Приговор № 1-120/2026 ..." -> "приговор";
    "Апелляционное определение № ..." -> "апелляционное определение".
    """
    if not title:
        return None
    match = _ACT_KIND.match(title.strip())
    if not match:
        return None
    kind = " ".join(match.group(1).lower().split())
    return kind or None


def extract_case_number(title: str) -> str | None:
    match = _CASE_NUMBER.search(title or "")
    return match.group(1) if match else None


def extract_uid(text: str) -> str | None:
    match = _UID.search(text or "")
    if not match:
        return None
    uid = match.group(1).rstrip("-")
    return uid if len(uid) >= 12 else None


def extract_decision_date(title: str) -> date | None:
    match = _TITLE_DATE.search(title or "")
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def extract_articles(text: str) -> list[str]:
    """Unique Criminal Code article numbers mentioned in the act, in order.

    Informational only: qualification keys for cards are extracted later by
    the shared verdict reader, not here.
    """
    seen: list[str] = []
    for match in _ARTICLE.finditer(text or ""):
        article = match.group(1)
        if article not in seen:
            seen.append(article)
    return seen


def split_court(court_line: str) -> tuple[str | None, str | None]:
    """Split "Суд (Регион)" into the court and the region."""
    if not court_line:
        return None, None
    line = " ".join(court_line.split())
    match = re.search(r"^(.*?)\s*\(([^()]+)\)\s*$", line)
    if not match:
        return line or None, None
    return match.group(1).strip() or None, match.group(2).strip() or None
