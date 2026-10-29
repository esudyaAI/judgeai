"""Integration: knowledge verdicts -> cards -> three channels -> filters and score -> API."""

from sqlalchemy import func, select

from src.application.precedent_cards import CARD_EXTRACTOR_VERSION, build_card
from src.application.similar_precedents import FindSimilarPrecedents, IndexPrecedents
from src.cli.precedents import run_index
from src.db.models import KnowledgeVerdict
from src.db.precedents import PrecedentCardField, PrecedentCardRow, PrecedentEmbedding
from src.db.session import async_session_factory
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import RegexVerdictReader
from tests.fixtures.fake_embedder import HashingEmbedder
from tests.fixtures.synthetic_verdicts import (
    MULTI_COUNT,
    PRACTICE_ROBBERY,
    PRACTICE_THEFT,
    SINGLE_CONDITIONAL,
)

SIMILAR_THEFT = PRACTICE_THEFT.replace("ноутбук стоимостью\n55 000", "планшет стоимостью\n30 000")


async def _add_verdicts(*texts, source_type="manual"):
    async with async_session_factory() as db:
        for index, text in enumerate(texts):
            db.add(
                KnowledgeVerdict(
                    raw_text=text,
                    source_type=source_type,
                    uid=f"uid-{source_type}-{index}",
                    court_name="Условный районный суд",
                )
            )
        await db.commit()


async def _index(embedder=None):
    embedder = embedder or HashingEmbedder()
    async with async_session_factory() as db:
        use_case = IndexPrecedents(SqlPrecedentStore(db), RegexVerdictReader(), embedder)
        return await use_case.execute(CARD_EXTRACTOR_VERSION)


async def _count(model):
    async with async_session_factory() as db:
        return await db.scalar(select(func.count()).select_from(model))


async def test_index_is_idempotent_and_deduplicates():
    await _add_verdicts(PRACTICE_THEFT, PRACTICE_ROBBERY, SIMILAR_THEFT)
    await _add_verdicts(PRACTICE_THEFT, source_type="sudact")  # same text from another source
    report = await _index()
    assert (report.cards, report.duplicates, report.vectors) == (3, 1, 3)
    again = await _index()
    assert (again.cards, again.duplicates, again.vectors) == (0, 1, 0)
    assert await _count(PrecedentCardRow) == 3
    assert await _count(PrecedentEmbedding) == 3
    assert await _count(PrecedentCardField) == 27


async def test_private_case_documents_are_never_indexed():
    await _add_verdicts(PRACTICE_THEFT, source_type="chat")
    report = await _index()
    assert report.cards == 0


async def test_stored_card_is_anonymised_and_has_field_quotes():
    await _add_verdicts(PRACTICE_THEFT)
    await _index()
    async with async_session_factory() as db:
        row = await db.scalar(select(PrecedentCardRow))
        assert row.qualification_keys == ["158/2/в"]
        assert row.imprisonment_months == 18 and row.conditional
        assert "2026" not in row.fabula and "М." not in row.fabula
        field = await db.scalar(
            select(PrecedentCardField).where(PrecedentCardField.name == "mitigating")
        )
        assert field.method == "regex" and "явку с повинной" in field.quote


async def test_embedding_failure_keeps_cards_searchable():
    class Broken(HashingEmbedder):
        async def embed_passages(self, texts):
            raise RuntimeError("model unavailable")

        async def embed_query(self, text):
            raise RuntimeError("model unavailable")

    await _add_verdicts(PRACTICE_THEFT, PRACTICE_ROBBERY)
    report = await _index(Broken())
    assert report.cards == 2 and report.vectors == 0 and "model unavailable" in report.vector_error
    query = build_card(RegexVerdictReader(), SINGLE_CONDITIONAL).card
    async with async_session_factory() as db:
        found = await FindSimilarPrecedents(SqlPrecedentStore(db), Broken()).execute(query)
    assert not found.vector_used
    assert [item.stored.card.main_qualification.article for item in found.items] == ["158"]


async def test_search_ranks_same_qualification_first_and_excludes_other_articles():
    await _add_verdicts(PRACTICE_THEFT, PRACTICE_ROBBERY, MULTI_COUNT)
    embedder = HashingEmbedder()
    await _index(embedder)
    query = build_card(RegexVerdictReader(), SINGLE_CONDITIONAL).card
    async with async_session_factory() as db:
        found = await FindSimilarPrecedents(SqlPrecedentStore(db), embedder).execute(query)
    assert found.vector_used
    assert found.excluded == 1  # the robbery (ст. 161) fails the article filter
    top = found.items[0]
    assert top.stored.card.main_qualification.key == "158/2/в"
    assert set(top.channels) == {"vector", "qualification", "fulltext"}
    assert top.breakdown["qualification"]["score"] == 1.0
    assert top.text_similarity is not None and 0 < top.text_similarity <= 1
    assert found.items[0].score > found.items[-1].score
    multi = found.items[-1]
    assert multi.stored.card.recidivism.value == "simple"
    assert any(f.name == "same_recidivism" and f.state.value == "failed" for f in multi.filters)


async def test_cli_index_runs(monkeypatch):
    await _add_verdicts(PRACTICE_THEFT)
    report = await run_index(HashingEmbedder())
    assert report["cards"] == 1 and report["vector_error"] is None


async def test_api_similar_precedents(client):
    from src.api.precedents import get_embedder
    from src.main import app

    await _add_verdicts(PRACTICE_THEFT, PRACTICE_ROBBERY)
    embedder = HashingEmbedder()
    await _index(embedder)
    app.dependency_overrides[get_embedder] = lambda: embedder
    try:
        chat_id = (await client.post("/api/chats", json={"title": "Кража"})).json()["id"]
        empty = (await client.get(f"/api/chats/{chat_id}/precedents")).json()
        assert empty["items"] == [] and empty["note"]
        await client.post(
            f"/api/chats/{chat_id}/messages",
            data={"content": "Проверь"},
            files=[("files", ("Проект.txt", SINGLE_CONDITIONAL.encode(), "text/plain"))],
        )
        r = await client.get(f"/api/chats/{chat_id}/precedents?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["query"]["qualifications"] == ["п. «в» ч. 2 ст. 158 УК РФ"]
        assert len(body["items"]) == 1 and body["excluded"] == 1
        item = body["items"][0]
        assert item["punishment_months"] == 18 and item["conditional"] is True
        assert "fabula" not in item
        assert {f["name"] for f in item["filters"]} == {
            "same_article",
            "same_part",
            "same_recidivism",
        }
    finally:
        app.dependency_overrides.pop(get_embedder, None)


async def test_api_hides_other_users_cases(client):
    from src.db.auth import User
    from src.db.models import Chat

    async with async_session_factory() as db:
        other = User(username="other-user", is_admin=False)
        db.add(other)
        await db.flush()
        chat = Chat(title="Чужое дело", owner_id=other.id)
        db.add(chat)
        await db.commit()
        foreign = chat.id
    assert (await client.get(f"/api/chats/{foreign}/precedents")).status_code == 404


async def test_api_without_embedding_model_still_answers(client):
    await _add_verdicts(PRACTICE_THEFT)
    await _index()
    chat_id = (await client.post("/api/chats", json={"title": "Кража"})).json()["id"]
    await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь"},
        files=[("files", ("Проект.txt", SINGLE_CONDITIONAL.encode(), "text/plain"))],
    )
    body = (await client.get(f"/api/chats/{chat_id}/precedents")).json()
    assert body["vector_used"] is False and len(body["items"]) == 1


async def test_explicit_refresh_preserves_ids_vectors_raw_text_and_old_field_evidence():
    from src.application.precedent_refresh import refresh_precedents
    from src.infrastructure.verdict_reader import PracticeReader

    await _add_verdicts(PRACTICE_THEFT)
    await _index()
    async with async_session_factory() as db:
        row = await db.scalar(select(PrecedentCardRow))
        card_id = row.id
        row.extractor_version = "precedent-card/2"
        row.mitigating = []
        fields = list(await db.scalars(select(PrecedentCardField)))
        for field in fields:
            field.extractor_version = "precedent-card/2"
        await db.commit()
        store = SqlPrecedentStore(db)
        dry = await refresh_precedents(store, PracticeReader(), CARD_EXTRACTOR_VERSION)
        assert dry.sources == 1 and dry.updated_cards == 0
        assert (await db.get(PrecedentCardRow, card_id)).mitigating == []
        result = await refresh_precedents(
            store, PracticeReader(), CARD_EXTRACTOR_VERSION, apply=True
        )
        assert result.updated_cards == 1
        await db.refresh(row)
        assert row.id == card_id and "61.1.и" in row.mitigating
        assert row.extractor_version == CARD_EXTRACTOR_VERSION
        assert await db.scalar(select(func.count()).select_from(PrecedentCardField)) == 18
        assert (await db.scalar(select(KnowledgeVerdict))).raw_text == PRACTICE_THEFT
        assert await db.scalar(select(func.count()).select_from(PrecedentEmbedding)) == 1
        again = await refresh_precedents(
            store, PracticeReader(), CARD_EXTRACTOR_VERSION, apply=True
        )
        assert again.sources == 0


async def test_refresh_inspection_rejects_shape_change_and_never_downgrades_future_version():
    from src.application.precedent_cards import build_cards
    from src.application.precedent_refresh import refresh_precedents
    from src.infrastructure.verdict_reader import PracticeReader

    await _add_verdicts(PRACTICE_THEFT)
    await _index()
    async with async_session_factory() as db:
        row = await db.scalar(select(PrecedentCardRow))
        row.extractor_version = "precedent-card/2"
        await db.commit()
        store = SqlPrecedentStore(db)
        source = (await store.stale_sources(CARD_EXTRACTOR_VERSION))[0]
        assert await store.can_refresh(source, []) is False
        assert await store.refresh_cards(source, []) is None
        await db.refresh(row)
        assert row.extractor_version == "precedent-card/2"
        row.extractor_version = "precedent-card/999"
        await db.commit()
        assert await store.stale_sources(CARD_EXTRACTOR_VERSION) == []
        assert await store.can_refresh(source, build_cards(PracticeReader(), source.text)) is False
        result = await refresh_precedents(
            store, PracticeReader(), CARD_EXTRACTOR_VERSION, apply=True
        )
        assert result.updated_cards == 0


async def test_refresh_adds_cards_for_people_an_older_extractor_merged(monkeypatch):
    from src.application.precedent_refresh import refresh_precedents
    from src.infrastructure.verdict_reader import PracticeReader
    from tests.fixtures.synthetic_verdicts import PRACTICE_TWO_DEFENDANTS

    await _add_verdicts(PRACTICE_TWO_DEFENDANTS)
    # the older extractor read the whole operative part as one person
    monkeypatch.setattr("src.infrastructure.verdict_reader.scoped_verdicts", lambda text: [])
    async with async_session_factory() as db:
        index = IndexPrecedents(SqlPrecedentStore(db), PracticeReader(), HashingEmbedder())
        await index.execute(CARD_EXTRACTOR_VERSION)
        row = await db.scalar(select(PrecedentCardRow))
        card_id = row.id
        row.extractor_version = "precedent-card/2"
        await db.commit()
    monkeypatch.undo()
    async with async_session_factory() as db:
        result = await refresh_precedents(
            SqlPrecedentStore(db), PracticeReader(), CARD_EXTRACTOR_VERSION, apply=True
        )
        rows = list(
            await db.scalars(select(PrecedentCardRow).order_by(PrecedentCardRow.defendant_no))
        )
    assert (result.updated_cards, result.needs_review) == (2, 0)
    assert [r.defendant_no for r in rows] == [0, 1]
    assert rows[0].id == card_id
    assert [r.conditional for r in rows] == [False, True]
