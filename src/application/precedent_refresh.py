"""Explicit refresh of derived cards; audit/dry-run first, no LLM or vector API calls."""

from dataclasses import dataclass
from typing import Protocol

from src.application.precedent_cards import CardExtraction, MultiVerdictReader, build_cards
from src.application.similar_precedents import VerdictSource


def prior_versions(version: str) -> tuple[str, ...]:
    prefix, number = version.rsplit("/", 1)
    return tuple(f"{prefix}/{n}" for n in range(1, int(number)))


class RefreshStore(Protocol):
    async def stale_sources(self, version: str) -> list[VerdictSource]: ...
    async def can_refresh(self, source: VerdictSource, cards: list[CardExtraction]) -> bool: ...
    async def refresh_cards(
        self, source: VerdictSource, cards: list[CardExtraction]
    ) -> int | None: ...


@dataclass(frozen=True)
class RefreshReport:
    sources: int
    eligible_cards: int
    updated_cards: int
    needs_review: int
    dry_run: bool


async def refresh_precedents(
    store: RefreshStore, reader: MultiVerdictReader, version: str, *, apply: bool = False
) -> RefreshReport:
    sources = await store.stale_sources(version)
    eligible = updated = review = 0
    for source in sources:
        try:
            cards = build_cards(reader, source.text)
        except Exception:
            review += 1
            continue
        if not cards:
            review += 1
            continue
        if not await store.can_refresh(source, cards):
            review += 1
            continue
        eligible += len(cards)
        if apply:
            changed = await store.refresh_cards(source, cards)
            if changed is None:
                review += 1
            else:
                updated += changed
    return RefreshReport(len(sources), eligible, updated, review, not apply)
