from legal_core.entities import MeasureUnit, PunishmentKind
from sqlalchemy import func, select

from src.db.models import LlmWindowExtraction
from src.db.session import async_session_factory
from src.services.llm_client import LLMError
from src.services.punishment_window_resolver import resolve_windows, term_from_reading

WINDOW = "назначить наказание в виде лишения свободы на срок, равный двум годам"


class CountingLlm:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    async def complete_json(self, system, user):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_reading_requires_literal_quote_and_known_kind():
    good = {"kind": "imprisonment", "years": 2, "quote": "лишения свободы"}
    assert term_from_reading(good, WINDOW).amount == 24
    assert term_from_reading({**good, "quote": "выдумано"}, WINDOW) is None
    assert term_from_reading({**good, "kind": "exile"}, WINDOW) is None
    assert term_from_reading({**good, "years": None}, WINDOW) is None


def test_reading_of_fine_hours_and_life():
    fine = term_from_reading({"kind": "fine", "rubles": 5000, "quote": "в виде"}, WINDOW)
    hours = term_from_reading({"kind": "compulsory_works", "hours": 200, "quote": "в виде"}, WINDOW)
    life = term_from_reading({"kind": "life_imprisonment", "quote": "в виде"}, WINDOW)
    assert (fine.amount, fine.unit) == (5000, MeasureUnit.RUBLES)
    assert (hours.amount, hours.unit) == (200, MeasureUnit.HOURS)
    assert life.kind is PunishmentKind.LIFE_IMPRISONMENT
    assert term_from_reading({"kind": "fine", "quote": "в виде"}, WINDOW) is None


async def test_window_is_sent_once_and_cached():
    llm = CountingLlm({"kind": "imprisonment", "years": 2, "quote": "лишения свободы"})
    async with async_session_factory() as db:
        first = await resolve_windows(db, llm, (WINDOW,))
        second = await resolve_windows(db, llm, (WINDOW,))
        rows = await db.scalar(select(func.count()).select_from(LlmWindowExtraction))
    assert llm.calls == 1 and rows == 1
    assert first[0][1].amount == 24 and second[0][1].amount == 24


async def test_llm_failure_is_not_cached():
    llm = CountingLlm(LLMError("down"))
    async with async_session_factory() as db:
        result = await resolve_windows(db, llm, (WINDOW,))
        rows = await db.scalar(select(func.count()).select_from(LlmWindowExtraction))
    assert result == [(WINDOW, None)] and rows == 0


class ConcurrentLlm:
    """Counts in-flight calls; answers after a short delay."""

    def __init__(self):
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = 0

    async def complete_json(self, system, user):
        import asyncio

        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.05)
            return {"kind": "imprisonment", "years": 2, "quote": "лишения свободы"}
        finally:
            self.in_flight -= 1


async def test_windows_are_resolved_concurrently_with_a_bound():
    from src.services.punishment_window_resolver import MAX_CONCURRENT_WINDOWS

    windows = tuple(f"{WINDOW}, эпизод {n}" for n in range(1, 7))
    llm = ConcurrentLlm()
    async with async_session_factory() as db:
        result = await resolve_windows(db, llm, windows)
        rows = await db.scalar(select(func.count()).select_from(LlmWindowExtraction))
    assert llm.calls == 6 and rows == 6
    # Parallel round-trips cut the wall-clock, but the gateway sees at most the bound.
    assert 1 < llm.max_in_flight <= MAX_CONCURRENT_WINDOWS
    assert [window for window, _ in result] == list(windows)
    assert all(term.amount == 24 for _, term in result)
