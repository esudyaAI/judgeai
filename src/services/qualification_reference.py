"""Adapter: use the shared criminal citation parser for statute lookups."""

from legal_core.entities import ArticleReference
from legal_core.precedents import FIRST_SPECIAL_PART_ARTICLE, parse_qualifications

__all__ = ["FIRST_SPECIAL_PART_ARTICLE", "parse_qualification_reference"]


def parse_qualification_reference(text: str | None) -> ArticleReference | None:
    qualifications = parse_qualifications(text or "")
    if not qualifications:
        return None
    qualification = qualifications[0]
    return ArticleReference(article=qualification.article, part=qualification.part)
