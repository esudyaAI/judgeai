"""T45.1 — GET /api/practice/facts: numbers counted by code over cards of the practice base."""

import httpx

from src.application.precedent_cards import CARD_EXTRACTOR_VERSION
from src.application.similar_precedents import IndexPrecedents
from src.db.models import KnowledgeVerdict
from src.db.session import async_session_factory
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import RegexVerdictReader
from src.main import app
from tests.fixtures.fake_embedder import HashingEmbedder
from tests.fixtures.synthetic_verdicts import PRACTICE_ROBBERY, PRACTICE_THEFT

ORIGINAL_TERM = "1 (один) год 6 (шесть) месяцев"
TERMS = [
    "1 (один) год",
    "1 (один) год 6 (шесть) месяцев",
    "2 (два) года",
    "2 (два) года 6 (шесть) месяцев",
    "3 (три) года",
]


def _theft(index: int, term: str) -> str:
    # A different term and thief make a different text, so the cards are not duplicates.
    return PRACTICE_THEFT.replace(ORIGINAL_TERM, term).replace("М.", f"М{index}.")


async def _add(texts, source_type="sudact"):
    async with async_session_factory() as db:
        for index, text in enumerate(texts):
            db.add(
                KnowledgeVerdict(
                    raw_text=text,
                    source_type=source_type,
                    uid=f"uid-{source_type}-{index}",
                    court_name="Условный районный суд",
                    structured={"source_url": f"https://example.invalid/{source_type}/{index}"},
                )
            )
        await db.commit()
    async with async_session_factory() as db:
        use_case = IndexPrecedents(SqlPrecedentStore(db), RegexVerdictReader(), HashingEmbedder())
        await use_case.execute(CARD_EXTRACTOR_VERSION)


async def test_average_term_is_counted_from_the_cards_with_sources(client):
    await _add([_theft(i, term) for i, term in enumerate(TERMS)] + [PRACTICE_ROBBERY])
    response = await client.get(
        "/api/practice/facts", params={"q": "Какой средний срок по ч. 2 ст. 158?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["method"] == "code"
    assert body["qualification"] == "ч. 2 ст. 158 УК РФ"
    assert (body["found"], body["counted"], body["excluded"], body["with_term"]) == (5, 5, 0, 5)
    assert body["enough_data"] is True
    assert body["mean_months"] == 24
    assert body["median_months"] == 24
    assert (body["min_months"], body["max_months"]) == (12, 36)
    assert body["conditional_share"] == 1.0
    assert sorted(s["months"] for s in body["sources"]) == [12, 18, 24, 30, 36]
    urls = {s["source_url"] for s in body["sources"]}
    assert urls == {f"https://example.invalid/sudact/{i}" for i in range(5)}
    assert all(s["uid"] and s["court_name"] for s in body["sources"])
    assert "среднее 2 г." in body["text"]


async def test_other_article_and_private_documents_are_not_counted(client):
    await _add([PRACTICE_ROBBERY])
    await _add([_theft(9, "3 (три) года")], source_type="chat")
    response = await client.get("/api/practice/facts", params={"q": "средний срок по ч. 2 ст. 158"})
    body = response.json()
    assert body["answered"] is True
    assert (body["found"], body["counted"]) == (0, 0)
    assert body["sources"] == []
    assert body["mean_months"] is None
    assert "нет приговоров" in body["text"]


async def test_not_a_fact_question_is_not_answered_by_guess(client):
    response = await client.get("/api/practice/facts", params={"q": "Расскажи про мошенничество"})
    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is False
    assert body["text"] is None
    assert body["sources"] == []
    assert body["hint"]


async def test_question_is_required_and_bounded(client):
    assert (await client.get("/api/practice/facts")).status_code == 422
    too_long = "средний срок по ч. 2 ст. 158 " * 100
    assert (await client.get("/api/practice/facts", params={"q": too_long})).status_code == 422


async def test_anonymous_user_is_refused():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as anonymous:
        response = await anonymous.get(
            "/api/practice/facts", params={"q": "средний срок по ч. 2 ст. 158"}
        )
    assert response.status_code == 401
