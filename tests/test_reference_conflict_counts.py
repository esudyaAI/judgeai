"""T15.17: конфликт справочных данных по отдельному составу проекта.

T15.16 закрыла конфликт редакций отказом: анализ не падает, статья помечается непроверенной.
Ветвь для составов резолютивной части (`count_references` в `analysis_runner`) тестом не
покрывалась. Проект с двумя составами: конфликт данных по одной статье не должен ни сорвать
анализ, ни отменить проверку другого состава, ни выдать конфликт за «санкция не найдена».
"""

from hashlib import sha256

from sqlalchemy import select

from src.db.models import CriminalArticleSanction, LegalProvision
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.criminal_sanction_import import import_criminal_sanctions
from src.services.legal_library import import_snapshot
from tests.test_criminal_sanctions import _manifest, _seed
from tests.test_sanction_edition_tie import SEED_MOMENT, _second_edition

TWO_COUNTS = """ПРИГОВОР
ИМЕНЕМ РОССИЙСКОЙ ФЕДЕРАЦИИ
Условный районный суд г. Примерска рассмотрел уголовное дело в отношении К.
У С Т А Н О В И Л:
К. тайно похитил имущество потерпевшего Б. и путём обмана завладел деньгами потерпевшей В.
На основании изложенного, руководствуясь ст. ст. 307-309 УПК РФ, суд
П Р И Г О В О Р И Л:
К. признать виновным в совершении преступлений, предусмотренных ч. 2 ст. 158,
ч. 2 ст. 159 УК РФ, и назначить ему наказание:
- по ч. 2 ст. 158 УК РФ в виде лишения свободы на срок 1 (один) год 6 (шесть) месяцев;
- по ч. 2 ст. 159 УК РФ в виде лишения свободы на срок 1 (один) год.
На основании ч. 2 ст. 69 УК РФ по совокупности преступлений путём частичного сложения
назначенных наказаний окончательно назначить К. наказание в виде лишения свободы на срок
2 (два) года с отбыванием наказания в исправительной колонии общего режима.
"""
DRAFT = ("files", ("Проект.txt", TWO_COUNTS.encode(), "text/plain"))
OTHER_RAW = b"synthetic second edition with article 159 only"
CHECK_PREFIX = "Назначенное наказание"


async def _copy_sanctions_158_to_159(provision_id: int, edition_id: int) -> None:
    """Synthetic fixture: the art. 158 sanctions of `edition_id` repeated as art. 159."""
    async with async_session_factory() as db:
        rows = (
            await db.scalars(
                select(CriminalArticleSanction)
                .join(LegalProvision, LegalProvision.id == CriminalArticleSanction.provision_id)
                .where(
                    CriminalArticleSanction.article == "158",
                    LegalProvision.edition_id == edition_id,
                )
            )
        ).all()
        assert rows, "fixture: art. 158 has sanctions in the seeded edition"
        for row in rows:
            db.add(
                CriminalArticleSanction(
                    provision_id=provision_id,
                    article="159",
                    part=row.part,
                    ordinal=row.ordinal,
                    kind=row.kind,
                    role=row.role,
                    min_value=row.min_value,
                    max_value=row.max_value,
                    unit=row.unit,
                    clause=row.clause,
                    parser_version=row.parser_version,
                )
            )
        await db.commit()


async def _provision_159(edition_id: int) -> int:
    async with async_session_factory() as db:
        return await db.scalar(
            select(LegalProvision.id).where(
                LegalProvision.edition_id == edition_id, LegalProvision.locator == "article.159"
            )
        )


async def _analysed(client) -> dict:
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat_id}/messages", data={"content": "Проверь проект"}, files=[DRAFT]
    )
    message = sent.json()["assistant_message"]["id"]
    polled = (await client.get(f"/api/chats/{chat_id}/messages/{message}")).json()
    assert polled["status"] == "completed", polled["error"]
    return polled["result"]


def _count_check(result: dict, qualification: str) -> dict:
    found = [
        c
        for c in result["legal_checks"]
        if c["norm"].startswith(CHECK_PREFIX) and c["norm"].endswith(f"· {qualification}")
    ]
    assert len(found) == 1, [c["norm"] for c in result["legal_checks"]]
    return found[0]


def _conflict_warnings(result: dict) -> list[str]:
    return [w for w in result["warnings"] if "конфликт данных о редакциях" in w and "Санкция" in w]


async def test_conflict_of_the_qualified_article_leaves_the_other_count_checked(client):
    """Art. 158 (also the model's qualification) has two editions at one moment; 159 has one."""
    first_id, _ = await _second_edition(SEED_MOMENT)
    await _copy_sanctions_158_to_159(await _provision_159(first_id), first_id)

    result = await _analysed(client)

    conflicts = _conflict_warnings(result)
    assert len(conflicts) == 1  # qualification and count name one article: one warning
    assert "ч. 2 ст. 158 УК РФ" in conflicts[0]
    assert not any("не найдена" in w for w in result["warnings"])
    assert _count_check(result, "ч. 2 ст. 158 УК РФ")["status"] == "insufficient_data"
    assert _count_check(result, "ч. 2 ст. 159 УК РФ")["status"] != "insufficient_data"
    assert result["sanctions_version"] is None
    assert result["sanction_article_versions"] is None


async def test_conflict_of_a_count_only_article_is_named_and_the_qualification_is_checked(client):
    """Only art. 159 — a count, not the model's qualification — is in conflict."""
    first_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, first_id)
    await _copy_sanctions_158_to_159(await _provision_159(first_id), first_id)
    data = _manifest().model_dump()
    data.update(
        raw_sha256=sha256(OTHER_RAW).hexdigest(),
        edition_label="Synthetic second edition, art. 159 only",
        provisions=[
            {
                "locator": "article.159",
                "title": "Статья 159. Мошенничество",
                "body": "Статья 159. Мошенничество без санкции в фикстуре.",
                "ordinal": 0,
            }
        ],
    )
    async with async_session_factory() as db:  # same retrieved_at as the seed: a tie for 159
        second, _ = await import_snapshot(db, SnapshotImport.model_validate(data), OTHER_RAW)
        await db.commit()
        second_id = second.id
    await _copy_sanctions_158_to_159(await _provision_159(second_id), first_id)

    result = await _analysed(client)

    conflicts = _conflict_warnings(result)
    assert len(conflicts) == 1
    assert "ч. 2 ст. 159 УК РФ" in conflicts[0]
    assert not any("158" in w for w in conflicts)
    assert not any("не найдена" in w for w in result["warnings"])
    assert _count_check(result, "ч. 2 ст. 158 УК РФ")["status"] != "insufficient_data"
    assert _count_check(result, "ч. 2 ст. 159 УК РФ")["status"] == "insufficient_data"
    assert any(c["norm"] == "Санкция ч. 2 ст. 158 УК РФ" for c in result["legal_checks"])
