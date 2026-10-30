"""Use case: read punishments the regex could not parse, by sending only short windows to the LLM.

Every reading is cached by (sha256 of the window, field, prompt version), including empty ones.
The model must quote the window literally; otherwise its reading is discarded.

Windows are resolved concurrently (bounded): a multi-episode verdict may need many short
LLM calls, and sequential round-trips made the analysis take minutes (T39). The bound keeps
the shared LLM gateway inside its rate limit; results keep the input order.
"""

import asyncio
import logging
import time
from hashlib import sha256

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LlmWindowExtraction
from src.services.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

FIELD = "imposed_punishment"
PROMPT_VERSION = "punishment-window/1"
# Concurrent gateway calls: enough to cut the wall-clock of many windows, small enough for
# the ~1 CPU server and the provider's per-key rate limit (429 is retried client-side).
MAX_CONCURRENT_WINDOWS = 3
SYSTEM_PROMPT = """Ты читаешь фрагмент резолютивной части приговора суда РФ.
Найди назначенное наказание и верни JSON-объект:
{"kind": "imprisonment|fine|compulsory_works|correctional_works|forced_labour|
          restriction_of_freedom|arrest|life_imprisonment|null",
 "years": число или null, "months": число или null, "hours": число или null,
 "rubles": число или null, "quote": "точная цитата из фрагмента с наказанием"}
Если срок или размер во фрагменте не указан числом — верни null в соответствующих полях.
Ничего не выдумывай."""


def window_hash(window: str) -> str:
    return sha256(window.encode("utf-8")).hexdigest()


def term_from_reading(reading: dict, window: str) -> PunishmentTerm | None:
    """Domain term from a model reading; None when the reading is empty, invalid or unquoted."""
    quote = reading.get("quote")
    if not isinstance(quote, str) or not quote.strip() or quote not in window:
        return None
    try:
        kind = PunishmentKind(reading.get("kind"))
    except ValueError:
        return None
    if kind is PunishmentKind.LIFE_IMPRISONMENT:
        return PunishmentTerm(kind)

    def number(name: str) -> float:
        value = reading.get(name)
        return value if isinstance(value, int | float) and value > 0 else 0

    if kind is PunishmentKind.FINE:
        rubles = number("rubles")
        return PunishmentTerm(kind, rubles, MeasureUnit.RUBLES) if rubles else None
    if number("hours"):
        return PunishmentTerm(kind, number("hours"), MeasureUnit.HOURS)
    months = number("years") * 12 + number("months")
    return PunishmentTerm(kind, months, MeasureUnit.MONTHS) if months else None


async def _cached_readings(db: AsyncSession, keys: list[str]) -> dict[str, dict]:
    if not keys:
        return {}
    rows = (
        await db.execute(
            select(LlmWindowExtraction.input_hash, LlmWindowExtraction.value).where(
                LlmWindowExtraction.input_hash.in_(keys),
                LlmWindowExtraction.field == FIELD,
                LlmWindowExtraction.prompt_version == PROMPT_VERSION,
            )
        )
    ).all()
    return {key: value for key, value in rows}


async def _read_window(
    llm: LLMClient, window: str, idx: int, total: int, semaphore: asyncio.Semaphore
) -> dict | None:
    async with semaphore:
        t_win = time.monotonic()
        logger.info("[WINDOWS] Window %d/%d CACHE MISS, querying LLM...", idx, total)
        try:
            reading = await llm.complete_json(SYSTEM_PROMPT, window)
        except LLMError as exc:
            logger.warning(
                "[WINDOWS] Window %d/%d LLM failed in %.2fs: %s",
                idx,
                total,
                time.monotonic() - t_win,
                exc,
            )
            return None
        logger.info(
            "[WINDOWS] Window %d/%d LLM finished in %.2fs",
            idx,
            total,
            time.monotonic() - t_win,
        )
        return reading


async def resolve_windows(
    db: AsyncSession, llm: LLMClient, windows: tuple[str, ...]
) -> list[tuple[str, PunishmentTerm | None]]:
    t_start = time.monotonic()
    logger.info("[WINDOWS] Resolving %d ambiguous window(s)...", len(windows))
    keys = [window_hash(window) for window in windows]
    cached = await _cached_readings(db, keys)
    misses = [
        (idx, window, key)
        for idx, (window, key) in enumerate(zip(windows, keys, strict=True), start=1)
        if key not in cached
    ]
    if cached:
        logger.info(
            "[WINDOWS] %d/%d window(s) from cache", len(windows) - len(misses), len(windows)
        )
    readings: dict[str, dict] = dict(cached)
    if misses:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WINDOWS)
        resolved = await asyncio.gather(
            *(_read_window(llm, window, idx, len(windows), semaphore) for idx, window, _ in misses)
        )
        for (_, _, key), reading in zip(misses, resolved, strict=True):
            if reading is None:
                continue
            # Empty readings are cached too: the window will not be re-asked.
            if isinstance(reading, dict):
                readings[key] = reading
                await db.execute(
                    insert(LlmWindowExtraction)
                    .values(
                        input_hash=key,
                        field=FIELD,
                        prompt_version=PROMPT_VERSION,
                        value=reading,
                    )
                    .on_conflict_do_nothing(constraint="uq_llm_window_extraction")
                )
        await db.commit()
    results = [
        (window, term_from_reading(readings[key], window) if key in readings else None)
        for window, key in zip(windows, keys, strict=True)
    ]
    logger.info(
        "[WINDOWS] All %d window(s) resolved in %.2fs",
        len(windows),
        time.monotonic() - t_start,
    )
    return results
