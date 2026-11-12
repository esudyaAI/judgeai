"""T15.5: результат анализа помнит версию справки, по которой сделаны замечания.

Версии — отпечатки T15.4 из БД (`catalog_version` каталога и `basis_version` правила). Анализ
записывает версию каталога в результат, а каждое замечание с ключом правила — версию основания
этого правила, чтобы отчёт (T14) и экран (T11) могли сверить, не изменилась ли справка после
анализа. Старые сохранённые результаты без этих полей читаются как `None`.
"""

from src.db.session import async_session_factory
from src.schemas.analysis import CaseAnalysis, LlmCaseFacts
from src.services.case_analyzer import assemble_analysis
from src.services.legal_rule_catalog import ReferenceVersions, reference_versions, rule_catalog
from tests.test_statute_sanction_analysis import PART_2


def _analyse(statute, facts, reference=None):
    return assemble_analysis(
        LlmCaseFacts.model_validate({"fabula": "Кража", **facts}),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=["Подсудимый действовал умышленно."],
        statute=statute,
        reference=reference,
    )


GUILT = {"legal_facts": {"guilt": {"value": "intentional", "quote": "действовал умышленно"}}}
REFERENCE = ReferenceVersions(
    catalog="sha256:" + "c" * 64,
    rules={"art15.category": "sha256:" + "a" * 64},
)


async def test_reference_versions_are_the_catalog_fingerprints():
    async with async_session_factory() as db:
        versions = await reference_versions(db)
        items = await rule_catalog(db)
    assert versions.catalog == items[0]["catalog_version"]
    assert versions.rules == {item["key"]: item["basis_version"] for item in items}


def test_analysis_without_reference_leaves_versions_empty():
    result = _analyse(PART_2, GUILT)
    assert result.reference_version is None
    assert all(check.basis_version is None for check in result.legal_checks)


def test_analysis_stamps_catalog_and_rule_versions():
    result = _analyse(PART_2, GUILT, reference=REFERENCE)
    checks = {check.norm: check for check in result.legal_checks}
    assert result.reference_version == REFERENCE.catalog
    assert checks["ст. 15 УК РФ"].basis_version == REFERENCE.rules["art15.category"]
    # a plain reading of the sanction text names no rule, so it has no basis version
    assert checks["Санкция ч. 2 ст. 158 УК РФ"].rule_key is None
    assert checks["Санкция ч. 2 ст. 158 УК РФ"].basis_version is None


def test_rule_missing_from_reference_gets_no_invented_version():
    result = _analyse(PART_2, GUILT, reference=ReferenceVersions(catalog=REFERENCE.catalog))
    checks = {check.norm: check for check in result.legal_checks}
    assert checks["ст. 15 УК РФ"].rule_key == "art15.category"
    assert checks["ст. 15 УК РФ"].basis_version is None


def test_results_stored_before_versions_still_load():
    stored = _analyse(PART_2, GUILT, reference=REFERENCE).model_dump(mode="json")
    stored.pop("reference_version")
    for check in stored["legal_checks"]:
        check.pop("basis_version")
    old = CaseAnalysis.model_validate(stored)
    assert old.reference_version is None
    assert all(check.basis_version is None for check in old.legal_checks)


async def test_completed_analysis_stores_current_reference_version(client):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь проект"},
        files=[
            ("files", ("Проект.txt", "Подсудимый действовал умышленно.".encode(), "text/plain"))
        ],
    )
    msg_id = r.json()["assistant_message"]["id"]
    message = (await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")).json()
    assert message["status"] == "completed", message["error"]
    result = message["result"]
    listing = (await client.get("/api/legal/rules")).json()
    rules = {item["key"]: item["basis_version"] for item in listing["items"]}
    assert result["reference_version"] == listing["version"]
    for check in result["legal_checks"]:
        expected = rules.get(check["rule_key"]) if check["rule_key"] else None
        assert check["basis_version"] == expected
