"""Query: structured sanctions of an article from the newest parsed edition, with provenance."""

from dataclasses import dataclass

from legal_core.entities import MeasureUnit, PunishmentKind, SanctionRole, StatutorySanction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CriminalArticleSanction, LegalEdition, LegalProvision
from src.domain.parser_versions import newest_parser_version
from src.schemas.criminal_sanctions import SanctionProvenance


@dataclass(frozen=True)
class StatuteSanctionReading:
    sanctions: list[StatutorySanction]
    provenance: SanctionProvenance


async def find_article_sanctions(
    db: AsyncSession, article: str, part: int | None = None
) -> StatuteSanctionReading | None:
    """Sanctions of the article (or of one part) from the article's newest reading.

    The reading — edition by `retrieved_at`, then parser version — is chosen for the whole
    article, as in the per-article version of the reference (T15.12). A part absent from that
    reading is not parsed (None): it is never read from an older edition or parser (T15.13).
    Parser versions are ordered by number, not as text (T15.14).
    """
    query = (
        select(CriminalArticleSanction, LegalProvision, LegalEdition)
        .join(LegalProvision, LegalProvision.id == CriminalArticleSanction.provision_id)
        .join(LegalEdition, LegalEdition.id == LegalProvision.edition_id)
        .where(CriminalArticleSanction.article == article)
        .order_by(
            LegalEdition.retrieved_at.desc(),
            CriminalArticleSanction.ordinal,
        )
    )
    rows = (await db.execute(query)).all()
    if not rows:
        return None
    newest_edition_id = rows[0][2].id
    rows = [item for item in rows if item[2].id == newest_edition_id]
    newest_version = newest_parser_version(row.parser_version for row, _, _ in rows)
    rows = [
        item
        for item in rows
        if item[0].parser_version == newest_version and (part is None or item[0].part == part)
    ]
    if not rows:
        return None
    _, provision, edition = rows[0]
    sanctions = [
        StatutorySanction(
            article=row.article,
            part=row.part,
            kind=PunishmentKind(row.kind),
            role=SanctionRole(row.role),
            min_value=row.min_value,
            max_value=row.max_value,
            unit=MeasureUnit(row.unit) if row.unit else None,
            clause=row.clause,
        )
        for row, _, _ in rows
    ]
    provenance = SanctionProvenance(
        edition_id=edition.id,
        edition_label=edition.label,
        source_url=edition.source_url,
        source_sha256=edition.source_sha256,
        verification_status=edition.verification_status,
        provision_locator=provision.locator,
        parser_version=newest_version,
    )
    return StatuteSanctionReading(sanctions=sanctions, provenance=provenance)
