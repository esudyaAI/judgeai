import io
from datetime import UTC, datetime
from zipfile import ZipFile

from src.infrastructure.report_docx import build_report_docx


def test_current_report_does_not_duplicate_single_episode_and_labels_check_values():
    comparison = {
        "total": 63,
        "with_term": 63,
        "recidivism": "none",
        "enough_data": True,
        "median_months": 32,
    }
    snapshot = {
        "human_review": {"status": "not_reviewed"},
        "analysis": {
            "fabula": "synthetic",
            "practice": comparison,
            "practice_episodes": [comparison],
            "precedents": [
                {
                    "card_id": 1,
                    "filters": [
                        {"name": "same_recidivism", "state": "passed", "reason": "none"},
                        {
                            "name": "same_recidivism",
                            "state": "failed",
                            "reason": "рецидив: dangerous",
                        },
                    ],
                }
            ],
            "legal_checks": [
                {"norm": "ст. 15 УК РФ", "status": "ok", "value": "medium"},
                {"norm": "ст. 18 УК РФ", "status": "ok", "value": "none"},
            ],
        },
    }
    artifact = build_report_docx(snapshot, 1, datetime(2026, 11, 4, tzinfo=UTC))
    with ZipFile(io.BytesIO(artifact)) as doc:
        xml = doc.read("word/document.xml").decode()
    assert xml.count("Размер выборки n: 63") == 1
    assert xml.count("Медиана, мес.: 32") == 1
    assert "Результат: средней тяжести" in xml and "Результат: отсутствует" in xml
    assert "Результат: medium" not in xml and "Результат: none" not in xml
    assert "Рецидив: отсутствует" in xml

    assert "Рецидив: совпадает — отсутствует" in xml
    assert "Рецидив: различается — рецидив: опасный" in xml
    assert "same_recidivism" not in xml and "passed" not in xml
