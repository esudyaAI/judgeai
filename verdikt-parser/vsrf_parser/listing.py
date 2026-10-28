"""Разбор HTML-листинга acts.json в структурированные карточки дел."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from lxml import html as lxml_html

from .models import ActListItem

CLAIM_HREF_RE = re.compile(r"/lk/practice/claims/([\w\-]+)")
PDF_HREF_RE = re.compile(r"/lk/practice/stor_pdf/([\w\-]+)")
DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
CASE_NUMBER_RE = re.compile(r"^[0-9A-ZА-ЯЁ][0-9A-ZА-ЯЁ\-/,\.]*$")
KEY_FACTS_RE = re.compile(
    r"Ключевые сведения\s*Вид судопроизводства:\s*(.*?)\s*"
    r"Инстанция:\s*(.*?)\s*"
    r"Судебная коллегия:\s*(.*?)\s*"
    r"Судья-докладчик:\s*(.*?)\s*(?:Показать|Смотреть|$)",
    re.S,
)
ITEM_CLASS_PREFIX = "CaseStyle_case_item__"


def _clean_text(raw: str) -> str:
    text = unescape(raw)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_listing(content_html: str) -> list[ActListItem]:
    """Разбирает поле content из acts.json на список карточек дел."""
    if not content_html:
        return []
    root = lxml_html.fromstring(f"<div>{content_html}</div>")
    items: list[ActListItem] = []
    seen: set[str] = set()
    for el in root.iter():
        cls = el.get("class") or ""
        if not cls.startswith(ITEM_CLASS_PREFIX):
            continue
        item = _parse_item(el)
        if item and item.claim_id not in seen:
            seen.add(item.claim_id)
            items.append(item)
    return items


def _parse_item(el: Any) -> ActListItem | None:
    claim_id: str | None = None
    case_number: str | None = None
    pdf_id: str | None = None
    act_type: str | None = None
    for a in el.iter("a"):
        href = a.get("href") or ""
        text = _clean_text(a.text_content() or "")
        m = CLAIM_HREF_RE.search(href)
        if m:
            if claim_id is None:
                claim_id = m.group(1)
                if text and CASE_NUMBER_RE.match(text):
                    case_number = text
            continue
        m = PDF_HREF_RE.search(href)
        if m:
            if pdf_id is None:
                pdf_id = m.group(1)
                if text and text not in {"Посмотреть", "Скачать", "Смотреть"}:
                    act_type = text
    if not claim_id:
        return None
    text = _clean_text(el.text_content() or "")
    act_date_m = DATE_RE.search(text)
    proceeding = instance_label = collegium = reporter = None
    facts_m = KEY_FACTS_RE.search(text)
    if facts_m:
        proceeding = _clean_text(facts_m.group(1))
        instance_label = _clean_text(facts_m.group(2))
        collegium = _clean_text(facts_m.group(3))
        reporter = _clean_text(facts_m.group(4))
    return ActListItem(
        claim_id=claim_id,
        case_number=case_number,
        act_type=act_type,
        act_date=act_date_m.group(0) if act_date_m else None,
        pdf_id=pdf_id,
        proceeding=proceeding,
        instance_label=instance_label,
        collegium=collegium,
        reporter=reporter,
    )
