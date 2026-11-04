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
from datetime import UTC, datetime
from hashlib import sha256

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.llm_window_extractions import PrivateLlmWindowExtraction
from src.db.models import LlmWindowExtraction
from src.services.llm_client import LLMClient, LLMError, llm_provenance
from src.services.llm_receipts import capture_receipts

logger = logging.getLogger(__name__)

FIELD = "imposed_punishment"
PROMPT_VERSION = "punishment-window/2"
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


async def _cached_readings(
    db: AsyncSession, keys: list[str], chat_id: int | None = None
) -> dict[str, tuple[dict, dict | None]]:
    if not keys:
        return {}
    model = PrivateLlmWindowExtraction if chat_id is not None else LlmWindowExtraction
    query = select(model.input_hash, model.value, model.provenance).where(
        model.input_hash.in_(keys),
        model.field == FIELD,
        model.prompt_version == PROMPT_VERSION,
    )
    if chat_id is not None:
        query = query.where(PrivateLlmWindowExtraction.chat_id == chat_id)
    rows = (await db.execute(query)).all()
    return {key: (value, provenance) for key, value, provenance in rows}


async def _read_window(
    llm: LLMClient, window: str, idx: int, total: int, semaphore: asyncio.Semaphore
) -> tuple[dict, dict] | None:
    async with semaphore:
        t_win = time.monotonic()
        logger.info("[WINDOWS] Window %d/%d CACHE MISS, querying LLM...", idx, total)
        try:
            with capture_receipts() as receipts:
                reading = await llm.complete_json(SYSTEM_PROMPT, window)
        except LLMError as exc:
            logger.warning(
                "[WINDOWS] Window %d/%d LLM failed in %.2fs: %s",
                idx,
                total,
                time.monotonic() - t_win,
                type(exc).__name__,
            )
            return None
        logger.info(
            "[WINDOWS] Window %d/%d LLM finished in %.2fs",
            idx,
            total,
            time.monotonic() - t_win,
        )
        return reading, {
            "schema_version": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "prompt_version": PROMPT_VERSION,
            "system_prompt_sha256": window_hash(SYSTEM_PROMPT),
            "llm": {
                "mode": llm_provenance(llm)["mode"],
                "calls": receipts,
                "resolved_model_revision": None,
            },
        }


async def resolve_windows(
    db: AsyncSession,
    llm: LLMClient,
    windows: tuple[str, ...],
    *,
    chat_id: int | None = None,
    audit: list[dict] | None = None,
) -> list[tuple[str, PunishmentTerm | None]]:
    t_start = time.monotonic()
    logger.info("[WINDOWS] Resolving %d ambiguous window(s)...", len(windows))
    keys = [window_hash(window) for window in windows]
    cached = await _cached_readings(db, keys, chat_id)
    misses = [
        (idx, window, key)
        for idx, (window, key) in enumerate(zip(windows, keys, strict=True), start=1)
        if key not in cached
    ]
    if cached:
        logger.info(
            "[WINDOWS] %d/%d window(s) from cache", len(windows) - len(misses), len(windows)
        )
    readings = dict(cached)
    if misses:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_WINDOWS)
        resolved = await asyncio.gather(
            *(_read_window(llm, window, idx, len(windows), semaphore) for idx, window, _ in misses)
        )
        for (_, _, key), result in zip(misses, resolved, strict=True):
            if result is None:
                continue
            reading, provenance = result
            # Empty readings are cached too: the window will not be re-asked.
            if isinstance(reading, dict):
                readings[key] = (reading, provenance)
                await db.execute(
                    insert(
                        PrivateLlmWindowExtraction if chat_id is not None else LlmWindowExtraction
                    )
                    .values(
                        input_hash=key,
                        field=FIELD,
                        prompt_version=PROMPT_VERSION,
                        value=reading,
                        provenance=provenance,
                        **({"chat_id": chat_id} if chat_id is not None else {}),
                    )
                    .on_conflict_do_nothing(
                        constraint=(
                            "uq_private_llm_window_extraction"
                            if chat_id is not None
                            else "uq_llm_window_extraction"
                        )
                    )
                )
        await db.commit()
    results = [
        (window, term_from_reading(readings[key][0], window) if key in readings else None)
        for window, key in zip(windows, keys, strict=True)
    ]
    if audit is not None:
        audit.extend(
            {
                "input_hash": key,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": key in cached,
                "provenance": readings[key][1] if key in readings else None,
            }
            for key in keys
        )
    logger.info(
        "[WINDOWS] All %d window(s) resolved in %.2fs",
        len(windows),
        time.monotonic() - t_start,
    )
    return results
