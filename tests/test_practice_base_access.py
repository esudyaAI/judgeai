"""The shared practice base is open to every signed-in user; only administrators delete."""

from src.db.models import KnowledgeVerdict
from src.db.session import async_session_factory
from tests.fixtures.synthetic_verdicts import PRACTICE_THEFT, SINGLE_CONDITIONAL
from tests.test_auth import account, anonymous, login


async def _ordinary(client):
    await account("alice")
    await login(client, "alice")


async def test_ordinary_user_uploads_lists_and_reads_practice():
    async with anonymous() as client:
        await _ordinary(client)
        r = await client.post(
            "/api/knowledge/verdicts/upload",
            files=[("files", ("v.txt", PRACTICE_THEFT.encode(), "text/plain"))],
        )
        assert r.status_code == 200, r.text
        verdict_id = r.json()["items"][0]["verdict_id"]
        assert r.json()["items"][0]["precedent"]["qualifications"]
        assert (await client.get("/api/knowledge/verdicts")).json()["total"] == 1
        assert (await client.get(f"/api/knowledge/verdicts/{verdict_id}")).status_code == 200


async def test_ordinary_user_cannot_delete_shared_practice():
    async with async_session_factory() as db:
        verdict = KnowledgeVerdict(raw_text=PRACTICE_THEFT, source_type="manual")
        db.add(verdict)
        await db.commit()
        verdict_id = verdict.id
    async with anonymous() as client:
        await _ordinary(client)
        r = await client.delete(f"/api/knowledge/verdicts/{verdict_id}")
        assert r.status_code == 403 and "администратор" in r.json()["detail"].lower()


async def test_ordinary_user_analysis_searches_practice():
    async with anonymous() as client:
        await _ordinary(client)
        chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
        r = await client.post(
            f"/api/chats/{chat_id}/messages",
            data={"content": "Проверь", "use_knowledge_base": "true"},
            files=[("files", ("draft.txt", SINGLE_CONDITIONAL.encode(), "text/plain"))],
        )
        assert r.status_code == 202, r.text
        msg_id = r.json()["assistant_message"]["id"]
        message = (await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")).json()
        assert message["status"] == "completed", message["error"]
        assert message["result"]["precedent_source"] == "none"  # searched, nothing to find


async def test_private_case_documents_never_reach_other_users():
    """A document saved from Alice's case stays out of the shared list and the text search."""
    from src.services.similarity_search import find_similar_verdicts

    secret = "Секретный протокол допроса свидетеля Смирнова по делу о краже автомобиля"
    async with async_session_factory() as db:
        db.add(KnowledgeVerdict(raw_text=secret, source_type="chat", source_filename="alice.txt"))
        db.add(KnowledgeVerdict(raw_text=PRACTICE_THEFT, source_type="manual"))
        await db.commit()
        # chunks are what the text search reads
        from src.db.models import KnowledgeChunk

        for v in (await db.scalars(__import__("sqlalchemy").select(KnowledgeVerdict))).all():
            db.add(KnowledgeChunk(verdict_id=v.id, chunk_type="text", content=v.raw_text))
        await db.commit()
        found = await find_similar_verdicts(db=db, query_text="протокол допроса свидетеля")
    assert all("Секретный" not in (item["excerpt"] or "") for item in found)
    async with anonymous() as client:
        await _ordinary(client)
        listing = (await client.get("/api/knowledge/verdicts")).json()
        assert listing["total"] == 1 and "alice.txt" not in str(listing)


async def test_upload_matching_a_private_document_creates_a_shared_one():
    """Uploading text that equals another user's case document must not reveal that document."""
    from src.services.knowledge_service import calculate_text_hash

    async with async_session_factory() as db:
        private = KnowledgeVerdict(
            raw_text=PRACTICE_THEFT,
            source_type="chat",
            source_filename="alice-case.txt",
            case_number="1-777/2026",
            file_hash=calculate_text_hash(PRACTICE_THEFT),
        )
        db.add(private)
        await db.commit()
        private_id = private.id
    async with anonymous() as client:
        await _ordinary(client)
        r = await client.post(
            "/api/knowledge/verdicts/upload",
            files=[("files", ("bob.txt", PRACTICE_THEFT.encode(), "text/plain"))],
        )
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["verdict_id"] != private_id
        assert item["duplicate"] is False and "alice-case" not in r.text and "1-777" not in r.text
        assert (await client.get("/api/knowledge/verdicts")).json()["total"] == 1


async def test_private_case_document_cannot_be_read_by_id():
    """Guessing the id of a document saved from another user's case returns nothing of it."""
    async with async_session_factory() as db:
        private = KnowledgeVerdict(
            raw_text="Протокол допроса свидетеля Смирнова",
            source_type="chat",
            source_filename="alice-case.txt",
        )
        db.add(private)
        await db.commit()
        private_id = private.id
    async with anonymous() as client:
        await _ordinary(client)
        r = await client.get(f"/api/knowledge/verdicts/{private_id}")
        assert r.status_code == 404
        assert "Смирнова" not in r.text and "alice-case" not in r.text


async def test_private_case_documents_never_reach_the_vector_search(monkeypatch):
    """Same boundary for the vector branch: a private chunk closest to the query stays out."""
    from src.config import settings
    from src.db.models import KnowledgeChunk
    from src.services import similarity_search
    from tests.fixtures.fake_embedder import HashingEmbedder

    embedder = HashingEmbedder()
    monkeypatch.setattr(similarity_search, "embed_query", embedder.embed_query)
    secret = "Секретный протокол допроса свидетеля Смирнова по делу о краже автомобиля"
    async with async_session_factory() as db:
        for text, source_type in ((secret, "chat"), (PRACTICE_THEFT, "manual")):
            verdict = KnowledgeVerdict(raw_text=text, source_type=source_type)
            db.add(verdict)
            await db.flush()
            [vector] = await embedder.embed_passages([text])
            db.add(
                KnowledgeChunk(
                    verdict_id=verdict.id,
                    chunk_type="text",
                    content=text,
                    embedding=vector,
                    embedding_model=settings.EMBEDDING_MODEL,
                )
            )
        await db.commit()
        found = await similarity_search.find_similar_verdicts(db=db, query_text=secret)
    assert found and all("Секретный" not in (item["excerpt"] or "") for item in found)
