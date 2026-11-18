"""Adapter (T45.3): sanctions of a part of an article from the law base, for fact answers."""

from legal_core.entities import StatutorySanction
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.sanction_facts import SanctionSource
from src.services.criminal_sanction_lookup import find_article_sanctions


class SqlSanctionReadings:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def article_sanctions(
        self, article: str, part: int | None
    ) -> tuple[list[StatutorySanction], SanctionSource] | None:
        reading = await find_article_sanctions(self._db, article, part)
        if reading is None:
            return None
        provenance = reading.provenance
        source = SanctionSource(
            edition_label=provenance.edition_label,
            source_url=provenance.source_url,
            provision_locator=provenance.provision_locator,
            verification_status=provenance.verification_status,
            effective_from=reading.effective_from,
            effective_to=reading.effective_to,
        )
        return reading.sanctions, source
