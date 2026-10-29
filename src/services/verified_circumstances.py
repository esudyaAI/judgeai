"""Validate model circumstances against court findings before any sentencing arithmetic."""

import re

from src.infrastructure.circumstance_extractor import extract_circumstances
from src.schemas.analysis import Circumstance
from src.services.verdict_segmenter import segment_verdict


def read_court_circumstances(text: str):
    parts = segment_verdict(text)
    return extract_circumstances(parts.description, parts.operative, parts.introduction)


def _norm(code: str) -> str:
    article, part, *point = code.split(".")
    if point and point[0].isdigit():
        return f"ч. {part}.{point[0]} ст. {article}"
    return (f"п. «{point[0]}» " if point else "") + f"ч. {part} ст. {article}"


def _codes(norm: str) -> set[str]:
    match = re.search(r"ч\.?\s*(\d(?:\.\d)?)\s*ст\.?\s*(61|63)(?!\d)", norm, re.I)
    if not match:
        return set()
    points = re.findall(r'[«"“]([а-яё])[»"”]', norm[: match.start()], re.I)
    base = f"{match[2]}.{match[1]}"
    return {f"{base}.{p.lower()}" for p in points} if points else {base}


def verified_circumstances(items: list[Circumstance], text: str, *, mitigating: bool):
    reading = read_court_circumstances(text)
    findings = reading.mitigating if mitigating else reading.aggravating
    verified, used = [], set()
    rejected = 0
    for item in items:
        codes = _codes(item.norm)
        # A short positive quote cannot override the negation of its full court statement.
        if not codes or not codes <= findings.keys():
            rejected += 1
            continue
        quotes = [findings[code] for code in sorted(codes)]
        if item.quote and item.quote not in text:
            rejected += 1
            continue
        if len(set(quotes)) == 1:
            verified.append(item.model_copy(update={"quote": quotes[0]}))
        else:
            for code in sorted(codes):
                verified.append(
                    item.model_copy(update={"norm": _norm(code), "quote": findings[code]})
                )
        used |= codes
    for code, quote in findings.items():
        if code not in used:
            verified.append(
                Circumstance(
                    name="Обстоятельство из текста приговора", norm=_norm(code), quote=quote
                )
            )
    return verified, rejected


def confirmed_no_aggravating(text: str) -> bool:
    """An empty model list is not proof that the court found no aggravating circumstances."""
    from src.infrastructure.circumstance_extractor import circumstance_statements

    reading = read_court_circumstances(text)
    if reading.aggravating or (
        reading.recidivism is not None and reading.recidivism.value != "none"
    ):
        return False
    return any(
        re.search(
            r"отягчающ[^.;]{0,120}(?:не\s+(?:установлен|усматрива|имеется)|отсутству)", s, re.I
        )
        or re.search(r"не\s+(?:установил|усматривает)[^.;]{0,80}отягчающ", s, re.I)
        for s in circumstance_statements(text)
    )
