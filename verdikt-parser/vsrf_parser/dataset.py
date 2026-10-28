"""Сборка ML-датасета: фильтр по статьям УК + метка исхода из разобранных текстов."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ARTICLE_CHUNK_RE = re.compile(
    r"(?:УК\s+РФ\s*:\s*)?ст\.\s*(\d+(?:[./]\d+)*)\s*(?:ч\.\s*([\d,]+))?"
)


def normalize_articles(articles: list[str] | None) -> list[str]:
    """Приводит статьи к каноническому виду: ['ст. 105 ч. 2', 'ст. 69 ч. 3']."""
    found: set[str] = set()
    for chunk in articles or []:
        for m in ARTICLE_CHUNK_RE.finditer(chunk):
            num = m.group(1).replace("/", ".")
            parts = m.group(2) or ""
            if not parts:
                found.add(f"ст. {num}")
            else:
                for part in parts.split(","):
                    part = part.strip()
                    if part:
                        found.add(f"ст. {num} ч. {part}")
    return sorted(found)


def parse_article_filter(spec: str) -> list[tuple[str, str]]:
    """"105", "105.2", "105 ч.2,111" -> [(num, part|''), ...]."""
    result: list[tuple[str, str]] = []
    for piece in spec.split(","):
        piece = piece.strip()
        if not piece:
            continue
        piece = re.sub(r"ст\.?\s*", "", piece).strip()
        m = re.match(r"(\d+(?:[./]\d+)*)\s*(?:ч\.?\s*(\d+))?", piece)
        if not m:
            raise ValueError(f"Не распознана статья: {piece!r}")
        num = m.group(1).replace("/", ".")
        part = m.group(2) or ""
        result.append((num, part))
    return result


def record_matches(record: dict, filters: list[tuple[str, str]]) -> bool:
    arts = normalize_articles(record.get("articles"))
    parsed = set()
    for a in arts:
        m = re.match(r"ст\. (\d+(?:\.\d+)*)(?: ч\. (\d+))?", a)
        if m:
            parsed.add((m.group(1), m.group(2) or ""))
    for num, part in filters:
        for rec_num, rec_part in parsed:
            if rec_num != num:
                continue
            if not part or rec_part == part:
                return True
    return False


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def build_dataset(
    out_dir: Path,
    article_spec: str | None,
    text_field: str = "full",
    include_full_text: bool = True,
) -> dict:
    """Собирает ML-датасет: {текст акта, метка исхода, статьи, метаданные}."""
    metadata = load_jsonl(out_dir / "metadata.jsonl")
    parsed = load_jsonl(out_dir / "parsed.jsonl")
    filters = parse_article_filter(article_spec) if article_spec else []

    by_pdf: dict[str, dict] = {}
    for rec in parsed:
        src = rec.get("source_path") or ""
        pdf_id = Path(src).stem if src else None
        if pdf_id:
            by_pdf[pdf_id] = rec

    matched = 0
    with_texts = 0
    dataset: list[dict] = []
    label_counter: Counter = Counter()
    for meta in metadata:
        if filters and not record_matches(meta, filters):
            continue
        matched += 1
        pdf_id = meta.get("pdf_id")
        if not pdf_id or pdf_id not in by_pdf:
            continue
        parse = by_pdf[pdf_id]
        label = parse.get("outcome")
        if not label:
            continue
        text_path = out_dir / "texts" / f"{pdf_id}.txt"
        text = text_path.read_text(encoding="utf-8", errors="replace")
        if text_field == "operative" and parse.get("operative_part"):
            text = parse["operative_part"]
        with_texts += 1
        label_counter[label] += 1
        item = {
            "pdf_id": pdf_id,
            "claim_id": meta.get("claim_id"),
            "case_number": meta.get("case_number"),
            "articles": normalize_articles(meta.get("articles")),
            "instance": meta.get("instance"),
            "first_court": meta.get("first_court"),
            "first_act_type": meta.get("first_act_type"),
            "act_date": meta.get("final_date"),
            "act_kind": parse.get("act_kind"),
            "label": label,
            "outcome_verbs": parse.get("outcome_verbs"),
            "sentence": parse.get("sentence"),
            "convicted": parse.get("convicted"),
            "operative_part": parse.get("operative_part"),
        }
        if include_full_text:
            item["text"] = text
        dataset.append(item)

    return {
        "total_metadata": len(metadata),
        "matched": matched,
        "in_dataset": with_texts,
        "labels": dict(label_counter),
        "items": dataset,
    }


def save_dataset(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
