"""T15.16: конфликт редакций санкций — явный ответ, а не ошибка сервера.

После T15.14/T15.15 противоречие в данных (две редакции статьи с одной датой получения,
несравнимые версии парсера) закрывается отказом. Прежде отказ доходил до клиента как 500,
а анализ дела падал целиком. Теперь API отвечает 409 «конфликт справочных данных, проверка
не выполнена», а анализ завершается с предупреждением: санкция статьи не проверена, версия
данных санкций не зафиксирована — ни одна из противоречащих редакций не выбирается.
"""

from src.domain.reference_conflict import CONFLICT_DETAIL
from tests.test_analysis_reference_status import _analysed
from tests.test_sanction_edition_tie import SEED_MOMENT, _second_edition


async def test_sanctions_api_answers_conflict_not_server_error(client):
    await _second_edition(SEED_MOMENT)
    for params in ({"article": "158"}, {"article": "158", "part": 2}):
        response = await client.get("/api/legal/sanctions", params=params)
        assert response.status_code == 409
        assert response.json() == {"detail": CONFLICT_DETAIL}


async def test_coverage_answers_conflict_not_server_error(client):
    await _second_edition(SEED_MOMENT)
    response = await client.get("/api/legal/rules/coverage")
    assert response.status_code == 409
    assert response.json() == {"detail": CONFLICT_DETAIL}


async def test_conflict_detail_is_russian_and_names_no_internal_ids():
    assert "Конфликт" in CONFLICT_DETAIL
    assert "не выполнена" in CONFLICT_DETAIL
    assert "same moment" not in CONFLICT_DETAIL


async def test_analysis_completes_with_warning_instead_of_failing(client):
    await _second_edition(SEED_MOMENT)
    _, _, result = await _analysed(client)
    assert result["sanctions_version"] is None
    assert result["sanction_article_versions"] is None
    assert any("158" in w and "конфликт" in w for w in result["warnings"])
    assert not any("не найдена" in w for w in result["warnings"])
    assert any("Версия справки" in w for w in result["warnings"])
