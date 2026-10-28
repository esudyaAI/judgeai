"""Структурный разбор текста судебного акта (приговор/определение/постановление)."""

from __future__ import annotations

import re
from pathlib import Path

from .models import ParsedActText

MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
MONTHS_RE = "|".join(MONTHS)

HYPHENATION_RE = re.compile(r"-\s*\n\s*")
SPACED_UPPER_RE = re.compile(r"(?<![А-ЯЁ])(?:[А-ЯЁ]\s){4,}[А-ЯЁ](?![а-яё])")
NEWLINE_RE = re.compile(r"\s*\n\s*")
MULTISPACE_RE = re.compile(r"[ \t]{2,}")

ACT_KIND_RE = re.compile(
    r"\b(КАССАЦИОННОЕ|АПЕЛЛЯЦИОННОЕ|НАДЗОРНОЕ|КАССАЦИОННЫЙ|АПЕЛЛЯЦИОННЫЙ|ЧАСТНАЯ)?\s*"
    r"(ОПРЕДЕЛЕНИЕ|ПОСТАНОВЛЕНИЕ|ПРИГОВОР|РЕШЕНИЕ|ЖАЛОБА)\b"
)
CASE_NUMBER_RE = re.compile(
    r"[Дд]ело\s*№?\s*"
    r"((?:[0-9A-Za-zА-ЯЁа-яё][0-9A-Za-zА-ЯЁа-яё\-/,.]*)"
    r"(?:\s+(?=[0-9A-ZА-ЯЁ]*[-0-9])[0-9A-Za-zА-ЯЁа-яё\-/]*)*)"
)
LONG_DATE_RE = re.compile(rf"(\d{{1,2}})\s+({MONTHS_RE})\s+(\d{{4}})\s*г", re.I)
SHORT_DATE_RE = re.compile(r"\b(\d{1,2}[.]\d{2}[.]\d{4})\b")
CITY_RE = re.compile(r"\bг\.\s?(Москва|Санкт-Петербург|[А-ЯЁ][а-яё]{2,})")
COLLEGIUM_RE = re.compile(
    r"[Сс]удебн\w+\s+коллеги\w+\s+по\s+(?:делам\s+)?"
    r"([а-яёА-ЯЁ\-(),\s]+?)\s*(?:Российской\s+Федерации\s*)?в\s+составе"
)
INITIALS = r"[А-ЯЁA-Z](?:[.\s]{0,2}[А-ЯЁA-Z])?[.\s]{0,2}"
PERSON_BODY = (
    rf"[А-ЯЁA-Z][а-яёa-z\-]+\s+{INITIALS}{INITIALS}?"
    rf"|[А-ЯЁA-Z][а-яёa-z\-]+\s+[А-ЯЁA-Z][а-яёa-z\-]+\s+[А-ЯЁA-Z][а-яёa-z]+"
)
NAME_RE = re.compile(PERSON_BODY)
PRESIDING_RE = re.compile(
    r"председательствующ(?:его|ей|им|ему|ая|ий)\s*[,:-]?\s*(" + PERSON_BODY + ")"
)
JUDGES_BLOCK_RE = re.compile(
    r"\bсуд(?:ей|ьям|ьями|ьё)\s*[,:-]?\s*(.{3,250}?)(?=,?\s*при\s+секретар|при\s+секретар|$)"
)
SECRETARY_RE = re.compile(
    r"при\s+секретар[еи]\s*[,:-]?\s*(" + PERSON_BODY + ")"
)
PROSECUTOR_RE = re.compile(
    r"прокурор(?:а|у|ом|ы)?\s+(" + PERSON_BODY + ")"
)
CONVICTED_RE = re.compile(
    r"осужд[ёе]нн\w*\s+(" + PERSON_BODY + ")",
)
LOWER_COURT_RE = re.compile(
    r"(?:приговор|постановление|решение)(?:ом|а)?\s+"
    r"([^,;()]{5,180}?\bсуд[ауе]?)\s+[^,;()]{0,80}?"
    r"(?:от|датирован\w+)\s*"
    r"(\d{1,2}\s+(?:" + MONTHS_RE + r")\s+\d{4}\s*г(?:ода)?"
    r"|\d{1,2}[.]\d{2}[.]\d{4})",
    re.I,
)
ARTICLE_WITH_PART_RE = re.compile(r"ч\.\s?(\d+(?:\.\d+)*)\s+ст\.\s?(\d+(?:[./]\d+)*)")
ARTICLE_ONLY_RE = re.compile(r"ст\.\s?(\d+(?:[./]\d+)*)(?:\s+ч\.\s?(\d+))?")
ARTICLE_WORD_RE = re.compile(
    r"стать[еяйм]\s+(\d+(?:\.\d+)*(?:/\d+)*)\s+(?:часть[юя]?\s+(\d+))?"
)
UK_CONTEXT_RE = re.compile(r"У\s?К|Уголовн\w+\s+кодекс")
OPERATIVE_RE = re.compile(
    r"(?:определ(?:ила|ил)|постановил(?:а|и)?|решил(?:а|и)?)\s*:\s*(.{20,2000})",
    re.I,
)
OUTCOME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("оставлен_без_изменения", re.compile(r"остав\w+\s+без\s+изменени\w+")),
    ("изменен", re.compile(r"измен(?:ить|ен(?:а|о|ы)?|ени\w+)", re.I)),
    ("отменен", re.compile(r"отмен(?:ить|ен(?:а|о|ы)?|ени\w+)", re.I)),
    (
        "передано_на_новое_рассмотрение",
        re.compile(
            r"(?:переда\w+|направ\w+|возвра\w+)\s+на\s+новое\s+"
            r"(?:судебное\s+)?(?:апелляционное\s+|кассационное\s+)?рассмотрени\w+"
        ),
    ),
    (
        "производство_прекращено",
        re.compile(r"производство\s+по\s+\S{0,30}\s*прекращ\w+"),
    ),
    ("возвращено", re.compile(r"возвра\w+")),
]
SENTENCE_RE = re.compile(
    r"к?\s*(\d+)\s+(год(?:а|у|е|ам|ом)?|лет)\s*"
    r"(?:(\d+)\s+(?:месяц\w*)\s*)?"
    r"(?:(\d+)\s+(?:дн\w+|сут\w+)\s*)?"
    r"лишения\s+свободы"
)
FREEDOM_DEATH_RE = re.compile(r"пожизненн\w+\s+лишени\w+\s+свободы")
COLLEGIUM_NOISE_RE = re.compile(
    r"(?:Верховного\s+Суда|Российской\s+Федерации|Верховным\s+Судом)\s*$"
)


def normalize(text: str) -> str:
    text = HYPHENATION_RE.sub("", text)
    text = SPACED_UPPER_RE.sub(lambda m: m.group(0).replace(" ", ""), text)
    text = NEWLINE_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" .,;")


def _dedup_lower(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = re.sub(r"[\s.]", "", item).lower()
        if key not in seen:
            seen.add(key)
            result.append(_clean(item))
    return [i for i in result if i]


def _parse_russian_date(raw: str) -> str | None:
    tokens = re.split(r"[\s]+", raw.strip())
    day: str | None = None
    year: str | None = None
    month: str | None = None
    for token in tokens:
        token_clean = token.strip(".")
        if token_clean.isdigit() and len(token_clean) == 4:
            year = token_clean
        elif token_clean.isdigit():
            day = token_clean.zfill(2)
        else:
            for idx, month_name in enumerate(MONTHS):
                if month_name.startswith(token_clean.lower()[:4]) and len(token_clean) >= 3:
                    month = f"{idx + 1:02d}"
                    break
        if day and year and month:
            break
    if day and month and year:
        return f"{day}.{month}.{year}"
    if day and year and len(tokens) == 3:
        return None
    return None


def _extract_articles(text: str) -> list[str]:
    found: list[str] = []

    def window_ok(start: int, end: int) -> bool:
        ctx = text[max(0, start - 90): min(len(text), end + 90)]
        return bool(UK_CONTEXT_RE.search(ctx))

    for m in ARTICLE_WITH_PART_RE.finditer(text):
        if window_ok(m.start(), m.end()):
            found.append(f"ст. {m.group(2)} ч. {m.group(1)} УК РФ")
    for m in ARTICLE_ONLY_RE.finditer(text):
        if window_ok(m.start(), m.end()):
            label = f"ст. {m.group(1)}"
            if m.group(2):
                label += f" ч. {m.group(2)}"
            found.append(f"{label} УК РФ")
    for m in ARTICLE_WORD_RE.finditer(text):
        if window_ok(m.start(), m.end()):
            label = f"ст. {m.group(1)}"
            if m.group(2):
                label += f" ч. {m.group(2)}"
            found.append(f"{label} УК РФ")
    return _dedup_lower(found)


def _extract_outcome(
    scope: str | None, text: str
) -> tuple[list[str], str | None]:
    target = scope if scope else text
    verbs: list[str] = []
    for name, pattern in OUTCOME_PATTERNS:
        if pattern.search(target):
            verbs.append(name)
    if not verbs:
        return [], None
    priority = [
        "отменен", "изменен", "оставлен_без_изменения",
        "передано_на_новое_рассмотрение", "производство_прекращено", "возвращено",
    ]
    verbs = [v for v in priority if v in verbs]
    return verbs, verbs[0]


def _humanize_years(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} года"
    return f"{n} лет"


def _humanize_months(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} месяц"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} месяца"
    return f"{n} месяцев"


def _humanize_days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} дня"
    return f"{n} дней"


def _extract_sentence(text: str) -> str | None:
    if FREEDOM_DEATH_RE.search(text):
        return "пожизненное лишение свободы"
    best: str | None = None
    best_score = -1.0
    for m in SENTENCE_RE.finditer(text):
        years = int(m.group(1))
        months = int(m.group(3) or 0)
        days = int(m.group(4) or 0)
        score = years + months / 12 + days / 365
        if score > best_score:
            best_score = score
            parts = [_humanize_years(years)]
            if months:
                parts.append(_humanize_months(months))
            if days:
                parts.append(_humanize_days(days))
            best = " ".join(parts) + " лишения свободы"
    return best


def _person_key(item: str) -> str:
    tokens = item.split()
    if not tokens:
        return item.lower()
    surname = tokens[0].lower()
    if len(surname) >= 6 and surname[-1] in "аеу":
        surname = surname[:-1]
    initial = tokens[1][0].lower() if len(tokens) > 1 and tokens[1] else ""
    return re.sub(r"[^а-яa-z]", "", surname + initial)


def parse_act_text(raw_text: str, source_path: str | None = None) -> ParsedActText:
    text = normalize(raw_text)
    head = text[:700]

    act_kind: str | None = None
    kind_m = ACT_KIND_RE.search(head)
    if kind_m:
        prefix = kind_m.group(1) or ""
        act_kind = _clean(f"{prefix} {kind_m.group(2)}".strip().lower())

    case_number: str | None = None
    num_m = CASE_NUMBER_RE.search(text)
    if num_m:
        case_number = num_m.group(1).replace(" ", "")

    act_date: str | None = None
    date_m = LONG_DATE_RE.search(head) or LONG_DATE_RE.search(text)
    if date_m:
        act_date = (
            f"{int(date_m.group(1)):02d}.{MONTHS.index(date_m.group(2).lower()) + 1:02d}"
            f".{date_m.group(3)}"
        )
    else:
        short_m = SHORT_DATE_RE.search(head)
        if short_m:
            act_date = short_m.group(1)

    city: str | None = None
    city_m = CITY_RE.search(head)
    if city_m:
        city = city_m.group(1)

    collegium: str | None = None
    coll_m = COLLEGIUM_RE.search(text[:2500])
    if coll_m:
        captured = _clean(coll_m.group(1))
        captured = COLLEGIUM_NOISE_RE.sub("", captured).strip()
        collegium = _clean(captured) or None
    if not collegium:
        dept_m = re.search(
            r"[Сс]удебн\w+\s+коллеги\w+\s+по\s+(?:делам\s+)?([а-яё\-\s]+?)\s*"
            r"(?=[,.;]|рассмотрела|изучив|в\s|Верховного)",
            text[:2500],
        )
        if dept_m:
            collegium = _clean(dept_m.group(1))

    presiding: str | None = None
    pres_m = PRESIDING_RE.search(text[:3000])
    if pres_m:
        presiding = _clean(pres_m.group(1))

    judges: list[str] = []
    block_m = JUDGES_BLOCK_RE.search(text[:3000])
    if block_m:
        judges = _dedup_lower(NAME_RE.findall(block_m.group(1)))[:5]

    secretary: str | None = None
    sec_m = SECRETARY_RE.search(text[:3500])
    if sec_m:
        secretary = _clean(sec_m.group(1))

    prosecutor: str | None = None
    proc_m = PROSECUTOR_RE.search(text[:4500])
    if proc_m:
        prosecutor = _clean(proc_m.group(1))

    convicted: list[str] = []
    for m in CONVICTED_RE.finditer(text):
        convicted.append(_clean(m.group(1)))
    seen_persons: set[str] = set()
    unique_convicted: list[str] = []
    for person in convicted:
        key = _person_key(person)
        if key and key not in seen_persons:
            seen_persons.add(key)
            unique_convicted.append(person)
    convicted = unique_convicted[:20]

    lower_court: str | None = None
    lower_court_date: str | None = None
    lc_m = LOWER_COURT_RE.search(text)
    if lc_m:
        lower_court = _clean(lc_m.group(1))
        lower_court_date = _parse_russian_date(lc_m.group(2))

    articles = _extract_articles(text)

    operative: str | None = None
    op_m = OPERATIVE_RE.search(text)
    if op_m:
        operative = _clean(op_m.group(1))[:800] or None
    outcome_scope = operative
    if not outcome_scope:
        tail = text[-900:]
        tail = re.sub(r"Председательствующ\w*\s*Судьи\s*$", "", tail).strip()
        if len(tail) >= 60:
            outcome_scope = tail

    outcome_verbs, outcome = _extract_outcome(outcome_scope, text)
    sentence = _extract_sentence(text)

    return ParsedActText(
        source_path=str(source_path) if source_path else None,
        act_kind=act_kind,
        case_number=case_number,
        act_date=act_date,
        city=city,
        collegium=collegium,
        presiding_judge=presiding,
        judges=judges,
        secretary=secretary,
        prosecutor=prosecutor,
        convicted=convicted,
        lower_court=lower_court,
        lower_court_date=lower_court_date,
        articles=articles,
        outcome=outcome,
        outcome_verbs=outcome_verbs,
        operative_part=operative,
        sentence=sentence,
        text_length=len(raw_text),
    )


def parse_act_file(path: Path) -> ParsedActText:
    return parse_act_text(path.read_text(encoding="utf-8"), source_path=str(path))
