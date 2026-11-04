import pytest
from legal_core.entities import ArticleReference

from src.domain.fact_review import FactDecision, InvalidReview, apply_decisions, review_catalog
from src.domain.review_evidence import Evidence
from src.infrastructure.calculation_inputs import capture_inputs, replay_inputs
from src.infrastructure.fact_review import FrozenReviewCalculator
from src.schemas.analysis import LlmCaseFacts
from src.services.verdict_structure import read_verdict_structure
from tests.test_statute_sanction_analysis import PART_2

TEXT = (
    "Подсудимый действовал умышленно. Суд признаёт явку с повинной смягчающим обстоятельством. "
    "Отягчающих обстоятельств не установлено.\nПРИГОВОРИЛ:\n"
    "По ч. 2 ст. 158 УК РФ назначить наказание в виде лишения свободы на срок 2 года. "
    "На основании ст. 73 УК РФ условно с испытательным сроком 2 года."
)
TERM = {"kind": "imprisonment", "amount": 72, "unit": "months"}


def saved(text=TEXT):
    sentence = read_verdict_structure([text], 30000).sentence
    assert sentence.counts
    return capture_inputs(
        LlmCaseFacts(fabula="synthetic", recommended_months=12),
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        sentence=sentence,
        statute=PART_2,
        count_statutes={ArticleReference("158", 2): PART_2},
    )


def edit(payload, field, value=None, *, operation="correct"):
    calculator = FrozenReviewCalculator()
    prepared = calculator.prepare(payload)
    doc = prepared.documents[0]
    evidence = (
        None
        if operation == "unknown"
        else Evidence(0, doc.document_hash, 0, len(doc.text), doc.text)
    )
    decisions = (
        FactDecision(f"subject/0/{field}", operation, "Синтетическая проверка", value, evidence),
    )
    legal, sentencing, audit, changed = apply_decisions(
        prepared.legal, prepared.sentencing, prepared.documents, prepared.context, decisions
    )
    updated, result = calculator.calculate(payload, legal, sentencing, changed)
    return updated, result, audit


def test_corrected_term_changes_actual_sanction_check_without_modifying_old_snapshot():
    payload = saved()
    original = replay_inputs(payload).model_dump(mode="json")
    updated, result, audit = edit(payload, "sentence/count/0/main", TERM)
    assert result["imposed_sentence"]["counts"][0]["imprisonment_months"] == 72
    assert any(
        c["status"] == "possible_violation" and "санкци" in c["norm"].lower()
        for c in result["legal_checks"]
    )
    assert audit[0]["old_value"]["amount"] == 24
    assert (
        updated["kwargs"]["prepared_sentencing_inputs"]["0"]["sentence"]["counts"][0]["main"][
            "amount"
        ]
        == 72
    )
    assert replay_inputs(payload).model_dump(mode="json") == original
    assert result["scale"]["recommended_months"] is None


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "fine", "amount": 20, "unit": "months"},
        {"kind": "compulsory_works", "amount": 20, "unit": "rubles"},
        {"kind": "life_imprisonment", "amount": 20, "unit": "months"},
        {"kind": "imprisonment", "amount": True, "unit": "months"},
        {"kind": "imprisonment", "amount": -1, "unit": "months"},
        {"kind": "imprisonment", "amount": 0, "unit": "months"},
        {"kind": "imprisonment", "amount": 20, "unit": None},
        {"kind": "imprisonment", "amount": float("nan"), "unit": "months"},
        {"kind": "imprisonment", "amount": float("inf"), "unit": "months"},
        {"kind": "imprisonment", "amount": 20, "unit": "months", "hidden": 1},
    ],
)
def test_term_boundary_validation_rejects_invalid_pairs_and_nonfinite_amounts(value):
    with pytest.raises(InvalidReview):
        edit(saved(), "sentence/count/0/main", value)


def test_unknown_main_does_not_show_or_calculate_latent_punishment():
    updated, result, _ = edit(saved(), "sentence/count/0/main", operation="unknown")
    count = result["imposed_sentence"]["counts"][0]
    assert (
        count["imprisonment_months"] is None
        and count["punishment"] == "Не установлено пользователем"
    )
    assert any(
        c["status"] == "insufficient_data" and "Основное наказание" in c["explanation"]
        for c in result["legal_checks"]
    )
    assert (
        next(c for c in result["legal_checks"] if c["norm"] == "ст. 73 УК РФ")["status"]
        == "insufficient_data"
    )
    assert "count/0/main" in updated["kwargs"]["prepared_sentencing_inputs"]["0"]["unknown_fields"]
    spec = next(
        s
        for s in review_catalog(
            FrozenReviewCalculator().prepare(updated).legal,
            FrozenReviewCalculator().prepare(updated).sentencing,
        )
        if s.id.endswith("sentence/count/0/main")
    )
    assert spec.value is None


def test_unknown_conditional_is_null_and_does_not_claim_a_real_sentence():
    updated, result, _ = edit(saved(), "sentence/conditional", operation="unknown")
    assert result["imposed_sentence"]["conditional"] is None
    assert any(
        c["norm"] == "ст. 73 / ст. 58 УК РФ" and c["status"] == "insufficient_data"
        for c in result["legal_checks"]
    )
    updated, known, _ = edit(updated, "sentence/conditional", False)
    assert known["imposed_sentence"]["conditional"] is False
    assert (
        "conditional" not in updated["kwargs"]["prepared_sentencing_inputs"]["0"]["unknown_fields"]
    )


def test_date_stage_probation_and_qualification_change_actual_inputs():
    payload = saved()
    payload, result, _ = edit(payload, "sentence/probation_months", 500)
    assert result["imposed_sentence"]["probation_months"] == 500
    assert (
        next(c for c in result["legal_checks"] if "ст. 73 УК РФ" in c["norm"])["status"]
        == "possible_violation"
    )
    payload, _, _ = edit(payload, "sentence/count/0/offence_date", "2024-02-29")
    assert (
        payload["kwargs"]["prepared_sentencing_inputs"]["0"]["sentence"]["counts"][0][
            "offence_date"
        ]
        == "2024-02-29"
    )
    payload, result, _ = edit(payload, "sentence/count/0/stage", operation="unknown")
    assert any(
        c["norm"].startswith("Стадия") and c["status"] == "insufficient_data"
        for c in result["legal_checks"]
    )
    payload, result, _ = edit(payload, "sentence/count/0/qualification", "ч. 1 ст. 161 УК РФ")
    assert payload["kwargs"]["statute"] is None and payload["facts"]["sanction_max_months"] is None
    assert (
        "161" in result["qualification"]["article"]
        and "158" not in result["qualification"]["article"]
    )
    assert result["scale"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("sentence/probation_months", True),
        ("sentence/probation_months", 1.5),
        ("sentence/count/0/offence_date", "2023-02-29"),
        ("sentence/count/0/qualification", "ст. 158 и ст. 161 УК РФ"),
        ("sentence/count/0/stage", False),
    ],
)
def test_typed_scalar_validation(field, value):
    with pytest.raises(InvalidReview):
        edit(saved(), field, value)


def test_new_counts_and_priors_preserve_old_indices_and_do_not_infer_missing_facts():
    payload = saved()
    payload, result, _ = edit(
        payload, "sentence/count/new", {"qualification": "ч. 1 ст. 161 УК РФ", "main": TERM}
    )
    assert len(result["imposed_sentence"]["counts"]) == 2
    prepared = payload["kwargs"]["prepared_sentencing_inputs"]["0"]
    assert prepared["sentence"]["counts"][1]["stage_conflict"] is True
    assert prepared["sentence"]["counts"][0]["main"]["amount"] == 24
    assert len(prepared["art64_by_count"]) == 2 and prepared["art64_by_count"][1]["value"] is None
    payload, _, _ = edit(
        payload, "prior/new", {"judgment_id": "SYNTHETIC-J1", "guilt": "intentional"}
    )
    prior = dict(payload["kwargs"]["prepared_legal_inputs"]["0"]["prior_convictions"][0])
    assert prior["judgment_id"]["value"] == "SYNTHETIC-J1"
    assert prior["active_at_offence"]["value"] is None


def test_unknown_circumstance_retains_entry_and_cannot_establish_absence():
    payload = saved()
    payload, result, _ = edit(
        payload,
        "circumstance/mitigating/new",
        {"name": "Явка с повинной", "norm": "п. и ч. 1 ст. 61 УК РФ", "established": True},
    )
    last = len(payload["kwargs"]["prepared_sentencing_inputs"]["0"]["mitigating"]) - 1
    payload, result, _ = edit(payload, f"circumstance/mitigating/{last}", operation="unknown")
    assert (
        payload["kwargs"]["prepared_sentencing_inputs"]["0"]["mitigating"][last]["established"]
        is None
    )
    payload, result, _ = edit(
        payload,
        "circumstance/aggravating/new",
        {
            "name": "Синтетическое обстоятельство",
            "norm": "п. а ч. 1 ст. 63 УК РФ",
            "established": True,
        },
    )
    assert payload["kwargs"]["prepared_sentencing_inputs"]["0"]["no_aggravating"]["value"] is None
    assert "Синтетическое обстоятельство" in result["aggravating"]
    payload, result, _ = edit(payload, "circumstance/aggravating/0", operation="unknown")
    assert "Синтетическое обстоятельство" not in result["aggravating"]
    assert any("неизвестной" in w for w in result["warnings"])


def test_human_guilt_for_aggregate_is_not_restored_from_original_text():
    payload = saved(
        TEXT.replace(
            "На основании ст. 73 УК РФ условно с испытательным сроком 2 года.",
            "По ч. 3 ст. 69 УК РФ окончательно назначить 3 года лишения свободы.",
        )
    )
    payload, _, _ = edit(payload, "legal/guilt", operation="unknown")
    assert (
        payload["kwargs"]["prepared_sentencing_inputs"]["0"]["guilt_by_count"][0]["value"] is None
    )
    result = replay_inputs(payload).model_dump(mode="json")
    assert any(
        c["status"] == "insufficient_data" and "69" in c["norm"] for c in result["legal_checks"]
    )


def test_additional_terms_and_optional_aggregate_term_unknown_are_explicit():
    payload = saved()
    fine = {"kind": "fine", "amount": 10000, "unit": "rubles"}
    payload, result, _ = edit(payload, "sentence/count/0/additional/new", fine)
    assert result["imposed_sentence"]["counts"][0]["additional"]
    payload, result, _ = edit(payload, "sentence/count/0/additional/0", operation="unknown")
    assert result["imposed_sentence"]["counts"][0]["additional"] == ["Не установлено пользователем"]
    payload, result, _ = edit(payload, "sentence/final", operation="unknown")
    assert result["imposed_sentence"]["final"] is None
    assert any(
        c["norm"].startswith("Совокупность") and c["status"] == "insufficient_data"
        for c in result["legal_checks"]
    )


async def test_actual_api_saves_term_objects_unknown_gates_and_structural_append(client):
    import io
    from uuid import uuid4
    from zipfile import ZipFile

    from tests.test_fact_review import proof
    from tests.test_review_sources import analysed

    path, base = await analysed(client)
    body = {
        "base_revision_id": base,
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/sentence/count/0/main",
                "operation": "correct",
                "value": TERM,
                "reason": "Проверен срок",
                "evidence": proof(),
            },
            {
                "fact_id": "subject/1/prior/new",
                "operation": "correct",
                "value": {"judgment_id": "intentional", "conditional_or_deferred": False},
                "reason": "Добавлен прежний приговор",
                "evidence": proof(),
            },
        ],
    }
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["defendants"][1]["imposed_sentence"]["counts"][0]["imprisonment_months"] == 72
    assert result["defendants"][0]["imposed_sentence"]["counts"][0]["imprisonment_months"] == 12
    detail = (await client.get(path + "/revisions/" + result["revision"]["id"])).json()
    prior = dict(
        detail["calculation_inputs"]["kwargs"]["prepared_legal_inputs"]["1"]["prior_convictions"][0]
    )
    assert prior["conditional_or_deferred"]["value"] is False
    assert prior["active_at_offence"]["value"] is None
    report = await client.post(path + "/reports")
    assert report.status_code == 201, report.text
    artifact = await client.get(f"/api/reports/{report.json()['id']}/docx")
    with ZipFile(io.BytesIO(artifact.content)) as doc:
        xml = doc.read("word/document.xml").decode()
    assert "Проверен срок" in xml and "Добавлен прежний приговор" in xml
    assert "лишение свободы" in xml and "kind" not in xml
    assert "Идентификатор прежнего приговора: intentional" in xml
    unknown = {
        "base_revision_id": result["revision"]["id"],
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/sentence/count/0/main",
                "operation": "unknown",
                "reason": "Данные противоречивы",
            }
        ],
    }
    cleared = await client.post(path + "/review", json=unknown)
    assert cleared.status_code == 200, cleared.text
    assert (
        cleared.json()["defendants"][1]["imposed_sentence"]["counts"][0]["imprisonment_months"]
        is None
    )
    wrong = {
        **body,
        "base_revision_id": cleared.json()["revision"]["id"],
        "client_request_id": str(uuid4()),
        "decisions": [dict(body["decisions"][0], fact_id="subject/0/sentence/count/0/main")],
    }
    assert (await client.post(path + "/review", json=wrong)).status_code == 422


def test_old_snapshot_without_count_guilt_is_replayable_but_not_editable():
    from src.domain.fact_review import ReviewConflict

    payload = saved()
    payload["kwargs"]["prepared_sentencing_inputs"]["0"].pop("guilt_by_count")
    assert replay_inputs(payload).imposed_sentence is not None
    with pytest.raises(ReviewConflict):
        FrozenReviewCalculator().prepare(payload)


def test_corrected_date_does_not_reuse_an_edition_without_temporal_metadata():
    payload, result, _ = edit(saved(), "sentence/count/0/offence_date", "2024-02-29")
    assert result["scale"] is None
    assert (
        next(c for c in result["legal_checks"] if c["norm"] == "ст. 15 УК РФ")["status"]
        == "insufficient_data"
    )
    assert any("Дата преступления изменена" in w for w in result["warnings"])
    assert "statute/0" in payload["kwargs"]["prepared_sentencing_inputs"]["0"]["unknown_fields"]


def test_absorption_unknown_is_not_inferred_from_old_text():
    payload = saved(
        TEXT.replace(
            "На основании ст. 73 УК РФ условно с испытательным сроком 2 года.",
            "По ч. 3 ст. 69 УК РФ окончательно назначить 3 года лишения свободы "
            "путём поглощения наказаний.",
        )
    )
    payload, result, _ = edit(payload, "sentence/absorption/final", operation="unknown")
    assert payload["kwargs"]["prepared_sentencing_inputs"]["0"]["aggregate_absorption"][1] is None
    assert any(
        c["norm"] == "Способ совокупности · ст. 69 УК РФ" and c["status"] == "insufficient_data"
        for c in result["legal_checks"]
    )


async def test_nonfinite_raw_json_is_invalid_input_and_does_not_write_a_revision(client):
    import json
    from uuid import uuid4

    from tests.test_fact_review import proof
    from tests.test_review_sources import analysed

    path, base = await analysed(client)
    body = {
        "base_revision_id": base,
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/sentence/count/0/main",
                "operation": "correct",
                "value": {**TERM, "amount": float("nan")},
                "reason": "PRIVATE-SYNTHETIC-NONFINITE",
                "evidence": proof(),
            }
        ],
    }
    response = await client.post(
        path + "/review", content=json.dumps(body), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422, response.text
    assert "PRIVATE-SYNTHETIC-NONFINITE" not in response.text
    assert len((await client.get(path + "/revisions")).json()) == 1
