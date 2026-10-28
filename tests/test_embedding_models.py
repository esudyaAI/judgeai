"""Vectors of different models live side by side; search reads only the configured model."""

from sqlalchemy import select

from src.db.models import KnowledgeChunk
from src.db.session import async_session_factory
from src.services import knowledge_service, similarity_search

TEXT = "Подсудимый тайно похитил ноутбук из квартиры потерпевшей и распорядился им."


async def _five_dimensions(texts):
    return [[1.0, 0.0, 0.0, 0.0, 0.0] for _ in texts]


async def _save(source_type="manual"):
    async with async_session_factory() as db:
        verdict, _ = await knowledge_service.create_knowledge_verdict_from_text(
            db, "a.txt", TEXT, source_type=source_type
        )
        await db.commit()
        return verdict.id


async def _chunk(verdict_id):
    async with async_session_factory() as db:
        return (
            await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.verdict_id == verdict_id))
        ).first()


async def test_chunks_keep_any_dimension_and_their_model(monkeypatch):
    monkeypatch.setattr(knowledge_service, "embed_passages", _five_dimensions)
    chunk = await _chunk(await _save())
    assert len(chunk.embedding) == 5
    assert chunk.embedding_model == knowledge_service.settings.EMBEDDING_MODEL


async def test_private_chat_uploads_are_never_sent_for_embedding(monkeypatch):
    sent = []

    async def spy(texts):
        sent.extend(texts)
        return [[1.0] for _ in texts]

    monkeypatch.setattr(knowledge_service, "embed_passages", spy)
    chunk = await _chunk(await _save(source_type="chat"))
    assert sent == []
    assert chunk.embedding is None and chunk.embedding_model is None


async def test_vector_search_ignores_vectors_of_another_model(monkeypatch):
    monkeypatch.setattr(knowledge_service, "embed_passages", _five_dimensions)
    await _save()
    query = [1.0, 0.0, 0.0, 0.0, 0.0]
    async with async_session_factory() as db:
        assert len(await similarity_search._vector_search(db, query, 3)) == 1
    monkeypatch.setattr(knowledge_service.settings, "EMBEDDING_MODEL", "another-model")
    async with async_session_factory() as db:
        assert await similarity_search._vector_search(db, query, 3) == []


async def test_reembed_replaces_vectors_of_the_previous_model_once(monkeypatch):
    monkeypatch.setattr(knowledge_service, "embed_passages", _five_dimensions)
    verdict_id = await _save()

    async def new_vectors(texts):
        return [[0.0, 1.0, 0.0] for _ in texts]

    monkeypatch.setattr(knowledge_service.settings, "EMBEDDING_MODEL", "new-model")
    monkeypatch.setattr(knowledge_service, "embed_passages", new_vectors)
    async with async_session_factory() as db:
        assert await knowledge_service.reembed_knowledge_chunks(db) == 1
        await db.commit()
    chunk = await _chunk(verdict_id)
    assert chunk.embedding_model == "new-model"
    assert [float(x) for x in chunk.embedding] == [0.0, 1.0, 0.0]
    async with async_session_factory() as db:
        assert await knowledge_service.reembed_knowledge_chunks(db) == 0
