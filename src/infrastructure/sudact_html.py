"""Adapter: HTML of a sudact.ru document page -> SudactDocument.

The act text lives in the left column (td.h-col1): after the <hr class="hr-h1">
divider and before the first service <h3> ("Суд:", "Судьи дела:"). Banners,
bookmark icons, scripts and the trailing reference blocks are skipped. Layout
variations fall back to the whole column, so text is never silently truncated.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser

from src.domain.sudact import (
    SudactDocument,
    extract_articles,
    extract_case_number,
    extract_decision_date,
    extract_uid,
    normalize_act_kind,
    split_court,
)

_SKIP_TAGS = frozenset({"script", "style", "noscript"})
# class fragments marking page furniture, never act text
_SKIP_CLASS_FRAGMENTS = ("adv", "banner", "bookmark", "spacer", "ya-context")
_VOID_TAGS = frozenset("br hr img input meta link area base col embed source track wbr".split())
_NEWLINE_TAGS = frozenset({"p", "h1", "h2", "h4", "li", "tr"})

_META_PATTERNS = (
    '<meta\\s+(?:name|property)="{key}"\\s+content="([^"]*)"',
    '<meta\\s+content="([^"]*)"\\s+(?:name|property)="{key}"',
)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_COURT_RE = re.compile(r"^(.*?суд[^(]*)\s*\(([^)]+)\)\s*-?\s*(уголовное)?", re.IGNORECASE)


class _ColumnParser(HTMLParser):
    """Collects text of td.h-col1 with furniture subtrees skipped.

    A tag stack (lenient to stray close tags) decides which subtrees are
    skipped, so nested ad divs cannot leak text into the act.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []  # (tag, is_skip)
        self.skip_count = 0
        self.column_depth = 0
        self.after_hr = False
        self.done = False
        self.text_parts: list[str] = []
        self.h1: list[str] = []
        self.in_h1 = 0
        self.headline_parts: list[str] = []

    @staticmethod
    def _classes(attrs) -> list[str]:
        return (dict(attrs).get("class") or "").lower().split()

    def _in_column(self) -> bool:
        return self.column_depth > 0 and not self.done

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _VOID_TAGS:
            if not self._in_column() or self.skip_count:
                return
            cls = self._classes(attrs)
            if tag == "hr" and "hr-h1" in cls:
                self.after_hr = True
            elif tag == "br":
                self._emit("\n")
            return
        cls = self._classes(attrs)
        if tag == "td" and any(c.startswith("h-col1") for c in cls):
            self.column_depth += 1
            self.stack.append((tag, False))
            return
        in_column = self._in_column()
        is_skip = bool(
            in_column
            and self.skip_count == 0
            and (tag in _SKIP_TAGS or any(f in c for c in cls for f in _SKIP_CLASS_FRAGMENTS))
        ) or (self.skip_count > 0)
        if in_column and self.skip_count == 0:
            if tag == "h3":
                # service block after the act: "Суд:", "Судьи дела:", ...
                self.done = True
                return
            if tag == "h1":
                self.in_h1 += 1
        if tag not in _VOID_TAGS:
            self.stack.append((tag, is_skip))
            if is_skip:
                self.skip_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if tag == "td" and self.column_depth:
            matching = next(
                (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == "td"),
                None,
            )
            if matching is None:
                return
            self._pop_to(matching)
            self.column_depth -= 1
            return
        matching = next(
            (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag),
            None,
        )
        if matching is None:
            return
        self._pop_to(matching)
        if self._in_column() and tag in _NEWLINE_TAGS and self.skip_count == 0:
            self._emit("\n")

    def _pop_to(self, index: int) -> None:
        while len(self.stack) > index:
            tag, is_skip = self.stack.pop()
            if is_skip:
                self.skip_count -= 1
            if tag == "h1":
                self.in_h1 = max(0, self.in_h1 - 1)

    def handle_data(self, data: str) -> None:
        if not self._in_column() or self.skip_count:
            return
        if self.in_h1:
            self.h1.append(data)
            return
        self._emit(data)

    def _emit(self, chunk: str) -> None:
        if self.after_hr:
            self.text_parts.append(chunk)
        else:
            self.headline_parts.append(chunk)

    @property
    def title(self) -> str:
        return " ".join("".join(self.h1).split())

    @property
    def text(self) -> str:
        source = self.text_parts if self.after_hr else self.headline_parts
        lines = [line.strip() for line in "".join(source).split("\n")]
        return "\n".join(line for line in lines if line)

    def headline_court(self) -> str | None:
        """The b-justice line ("Суд (Регион) - Уголовное") before the divider."""
        raw = " ".join(" ".join(self.headline_parts).split())
        match = _COURT_RE.search(raw)
        if not match:
            return None
        court, region = match.group(1).strip(), match.group(2).strip()
        return f"{court} ({region})" if region else court or None


def _meta_content(html: str, key: str) -> str | None:
    for pattern in _META_PATTERNS:
        match = re.search(pattern.format(key=key), html)
        if match:
            return unescape(match.group(1)).strip() or None
    return None


def _title_tag(html: str) -> str:
    match = _TITLE_RE.search(html)
    if not match:
        return ""
    title = unescape(match.group(1)).strip()
    suffix = ":: СудАкт.ру"
    if title.endswith(suffix):
        title = title[: -len(suffix)].strip()
    return title


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.replace("\xa0", " ").split()) or None


def parse_sudact_page(url: str, html: bytes, fetched_at: str | None = None) -> SudactDocument:
    fetched_at = fetched_at or datetime.now(UTC).isoformat(timespec="seconds")
    html_sha256 = hashlib.sha256(html).hexdigest()
    decoded = html.decode("utf-8", errors="replace")

    parser = _ColumnParser()
    parser.feed(decoded)
    parser.close()

    title = parser.title or _title_tag(decoded)
    text = parser.text.strip()

    court_name, region = split_court(_meta_content(decoded, "og:author") or "")
    if not court_name:
        court_name, region = split_court(parser.headline_court() or "")
    decision_date = extract_decision_date(title)
    uid = extract_uid(text)

    return SudactDocument(
        url=url,
        fetched_at=fetched_at,
        html_sha256=html_sha256,
        title=title,
        act_kind=normalize_act_kind(title) or "",
        case_number=extract_case_number(title),
        uid=uid,
        court_name=_clean(court_name),
        region=_clean(region),
        decision_date=decision_date.isoformat() if decision_date else None,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
        articles=extract_articles(text),
    )
