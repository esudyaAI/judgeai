"""Render only saved values; never invoke rules, a provider or a mutable practice store."""

import asyncio
import io

from docx import Document
from docx.shared import Cm, Pt

from src.domain.fact_review import PRIOR_LABELS
from src.domain.sentence_review import read_term
from src.services.sanction_summary import describe_term

_STATUS = {
    "ok": "Условия проверки подтверждены",
    "possible_violation": "Возможное нарушение",
    "insufficient_data": "Недостаточно данных",
}


_VALUE_LABELS = {
    "guilt": {"intentional": "умышленная", "negligent": "неосторожная"},
    "stage": {"completed": "оконченное", "attempt": "покушение", "preparation": "приготовление"},
    "category": {
        "small": "небольшой тяжести",
        "medium": "средней тяжести",
        "grave": "тяжкое",
        "especially_grave": "особо тяжкое",
    },
    "scope": {
        "count": "эпизод",
        "final": "окончательное наказание",
        "unassigned": "не установлена",
    },
    "status": {"stated": "указано в решении", "requires_review": "требует проверки"},
    "stated_recidivism": {
        "none": "отсутствует",
        "simple": "простой",
        "dangerous": "опасный",
        "especially_dangerous": "особо опасный",
    },
    "imposed": {
        "settlement": "колония-поселение",
        "general": "общий режим",
        "strict": "строгий режим",
        "special": "особый режим",
    },
    "recidivism": {
        "none": "отсутствует",
        "simple": "простой",
        "dangerous": "опасный",
        "especially_dangerous": "особо опасный",
    },
}


def _display(value, field=None):
    if value is None:
        return "не установлено"
    if isinstance(value, dict):
        if set(value) == {"kind", "amount", "unit"}:
            return describe_term(read_term(value))
        labels = {
            **PRIOR_LABELS,
            "qualification": "Квалификация",
            "main": "Основное наказание",
            "additional": "Дополнительные наказания",
            "stage": "Стадия",
            "offence_date": "Дата преступления",
            "name": "Обстоятельство",
            "norm": "Норма",
            "established": "Установлено",
            "scope": "Область зачёта",
            "count_index": "Эпизод",
            "original_amount": "Назначенный штраф",
            "reduced_amount": "Сумма после смягчения",
            "released": "Освобождение от отбывания",
            "status": "Статус чтения",
        }
        return "; ".join(
            f"{labels.get(key, key)}: {_display(item, key)}"
            for key, item in value.items()
            if key != "count_index" or item is not None or value.get("scope") == "count"
        )
    if isinstance(value, list):
        return "; ".join(_display(item) for item in value) or "не установлено"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if field == "count_index" and type(value) is int:
        return str(value + 1)
    values = _VALUE_LABELS.get(field, {})
    return values.get(value, str(value))


def _review_value(decision, key):
    return _display(decision.get(key), decision.get("fact_id", "").rsplit("/", 1)[-1])


def _subject(document, analysis):
    sentence = analysis.get("imposed_sentence") or {}
    if sentence:
        document.add_heading("Назначенное наказание", 2)
        for count in sentence.get("counts", []):
            document.add_paragraph(
                f"{count.get('qualification', '')}: {count.get('punishment', '')}"
            )
            for additional in count.get("additional", []):
                document.add_paragraph(f"Дополнительно: {additional}")
            if count.get("quote"):
                document.add_paragraph("Цитата: " + count["quote"])
        for key, title in [
            ("intermediate", "Промежуточный итог"),
            ("unserved", "Неотбытая часть"),
            ("joined", "Присоединено"),
            ("final", "Окончательное наказание"),
            ("credited", "Зачёт"),
            ("aggregation_rule", "Правило совокупности"),
            ("intermediate_rule", "Правило промежуточного итога"),
            ("prior_judgment_date", "Дата прежнего приговора"),
            ("probation_months", "Испытательный срок, мес."),
        ]:
            if sentence.get(key):
                document.add_paragraph(f"{title}: {sentence[key]}")
            elif key in sentence.get("unknown_fields", []):
                document.add_paragraph(f"{title}: не установлено пользователем")
        if sentence.get("conditional") is None and "conditional" in sentence.get(
            "unknown_fields", []
        ):
            document.add_paragraph("Условность осуждения не установлена пользователем.")
        if sentence.get("conditional"):
            document.add_paragraph("Условное осуждение указано в проекте.")
        for credit in sentence.get("fine_credits", []):
            if credit.get("unknown"):
                document.add_paragraph("Сведения о зачёте штрафа не установлены пользователем.")
                continue
            document.add_paragraph(
                "Зачёт штрафа: "
                + {
                    "count": "по составу",
                    "final": "по окончательному наказанию",
                    "unassigned": "область не установлена",
                }.get(credit.get("scope"), "область неизвестна")
                + f"; исходная сумма {_display(credit.get('original_amount'))}; "
                + f"уменьшенная сумма {_display(credit.get('reduced_amount'))}; "
                + f"освобождение {_display(credit.get('released'))}; "
                + {"stated": "указано в проекте", "requires_review": "требует проверки"}.get(
                    credit.get("status"), "статус неизвестен"
                )
                + "."
            )
            document.add_paragraph("Цитата: " + credit.get("quote", ""))
        for term in sentence.get("final_additional", []):
            document.add_paragraph("Окончательное дополнительное наказание: " + term)
        if sentence.get("final_quote"):
            document.add_paragraph("Цитата: " + sentence["final_quote"])
    for circumstance in analysis.get("mitigating", []):
        document.add_paragraph(
            f"Смягчающее обстоятельство: {circumstance.get('name')}; "
            f"норма: {circumstance.get('norm')}"
        )
        if circumstance.get("quote"):
            document.add_paragraph("Цитата: " + circumstance["quote"])
    if analysis.get("aggravating"):
        document.add_paragraph("Отягчающие обстоятельства: " + analysis["aggravating"])
    if analysis.get("personality"):
        document.add_paragraph("Данные о личности: " + analysis["personality"])
    document.add_heading("Проверки", 2)
    for check in analysis.get("legal_checks", []):
        document.add_paragraph(
            f"{check.get('norm', '')} — {_STATUS.get(check.get('status'), 'Не проверено')}",
            style="Heading 3",
        )
        document.add_paragraph(check.get("explanation") or "Обоснование отсутствует.")
        if check.get("value") is not None:
            field = {"ст. 15 УК РФ": "category", "ст. 18 УК РФ": "recidivism"}.get(
                check.get("norm")
            )
            document.add_paragraph("Результат: " + _display(check["value"], field))
        for quote in check.get("evidence", []):
            document.add_paragraph("Цитата: " + quote)
        document.add_paragraph("Источник: " + (check.get("source") or "неизвестен"))
        if check.get("needs_legal_review", True):
            document.add_paragraph("Норма и применимость требуют юридической проверки.")
    practice = analysis.get("practice_episodes") or (
        [analysis["practice"]] if analysis.get("practice") else []
    )
    if practice:
        document.add_heading("Сравнение с практикой", 2)
    for item in practice:
        for field, title in [
            ("total", "Размер выборки n"),
            ("with_term", "Срок прочитан"),
            ("qualification", "Квалификация"),
            ("recidivism", "Рецидив"),
            ("min_months", "Минимум, мес."),
            ("max_months", "Максимум, мес."),
            ("candidates", "Кандидаты до фильтрации"),
            ("conditional_share", "Доля условных наказаний"),
            ("art64_share", "Доля применения ст. 64"),
            ("art73_share", "Доля применения ст. 73"),
            ("draft_months", "Срок проекта, мес."),
            ("median_months", "Медиана, мес."),
            ("p25_months", "25-й перцентиль, мес."),
            ("p75_months", "75-й перцентиль, мес."),
            ("excluded", "Исключено"),
            ("draft_percentile", "Позиция проекта, перцентиль"),
        ]:
            value = item.get(field)
            document.add_paragraph(f"{title}: {_display(value, field)}")
        if not item.get("enough_data"):
            document.add_paragraph("Выборка недостаточна для уверенного сравнения.")
    for precedent in analysis.get("precedents") or []:
        document.add_paragraph(
            f"Прецедент {precedent.get('card_id')}: "
            f"{precedent.get('source_url') or 'источник неизвестен'}"
        )
        for item in precedent.get("filters") or []:
            name = {
                "same_article": "Статья",
                "same_part": "Часть статьи",
                "same_recidivism": "Рецидив",
            }.get(item.get("name"), "Критерий сопоставимости")
            state = {
                "passed": "совпадает",
                "failed": "различается",
                "uncertain": "не установлено",
            }.get(item.get("state"), "состояние неизвестно")
            reason = item.get("reason") or "обоснование отсутствует"
            if item.get("name") == "same_recidivism":
                reason = (
                    "рецидив: " + _display(reason.removeprefix("рецидив: "), "recidivism")
                    if reason.startswith("рецидив: ")
                    else _display(reason, "recidivism")
                )
            document.add_paragraph(f"{name}: {state} — {reason}")
    for warning in analysis.get("warnings") or []:
        document.add_paragraph("Ограничение: " + warning)


def _model_receipts(document, llm):
    document.add_paragraph(
        "Режим модели: "
        + {"synthetic": "синтетический пример", "external": "внешняя модель"}.get(
            llm.get("mode"), "неизвестен"
        )
    )
    for call in llm.get("calls", []):
        document.add_paragraph(
            f"Адаптер: {call.get('provider_adapter')}; "
            f"запрошенная модель: {call.get('requested_model') or 'неизвестна'}; "
            f"завершён: {call.get('completed_at')}"
        )
        document.add_paragraph("SHA-256 системного промпта: " + call["system_prompt_sha256"])


def build_report_docx(snapshot: dict, version: int, created_at) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Cm(2)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "Times New Roman", Pt(12)
    normal.paragraph_format.space_after = Pt(6)
    document.add_heading("Отчёт о проверке проекта приговора", 0)
    document.add_paragraph(f"Версия {version} · {created_at.isoformat()}")
    document.add_paragraph(
        "Предварительный результат. Не подтверждает законность приговора целиком."
    )
    review = snapshot.get("human_review") or {}
    document.add_paragraph(
        {
            "not_reviewed": "Не проверено человеком",
            "partially_reviewed": (
                "Часть фактов проверена пользователем; правовая приёмка не выполнена"
            ),
        }.get(review.get("status"), "Состояние проверки человеком неизвестно")
    )
    if review.get("decisions"):
        document.add_heading("Проверка фактов пользователем", 1)
        operations = {
            "confirm": "Подтверждено",
            "correct": "Исправлено",
            "unknown": "Не установлено",
        }
        for decision in review["decisions"]:
            document.add_paragraph(
                f"Осуждённый {decision.get('subject_index', 0) + 1}: "
                + (decision.get("field_label") or "Факт")
                + " — "
                + operations.get(decision.get("operation"), "Действие неизвестно")
            )
            document.add_paragraph(
                "Прежнее значение: "
                + _review_value(decision, "old_value")
                + "; новое значение: "
                + _review_value(decision, "new_value")
            )
            document.add_paragraph("Причина: " + (decision.get("reason") or "не указана"))
            document.add_paragraph(
                f"Пользователь {decision.get('actor_id', 'неизвестен')}; "
                + (decision.get("reviewed_at") or "время неизвестно")
            )
            evidence = decision.get("evidence")
            if evidence:
                document.add_paragraph("Цитата: " + evidence["quote"])
                document.add_paragraph(
                    f"Источник {evidence['document_index']}; Unicode-позиции "
                    f"{evidence['start']}–{evidence['end']}; SHA-256 " + evidence["document_hash"]
                )
    analysis = snapshot["analysis"]
    document.add_heading("Краткое содержание", 1)
    document.add_paragraph(analysis.get("fabula") or "Сводка отсутствует.")
    if analysis.get("qualification"):
        document.add_paragraph(analysis["qualification"].get("article") or "")
    _subject(document, analysis)
    for person in analysis.get("defendants") or []:
        document.add_heading(person.get("label") or "Осуждённый", 1)
        _subject(document, person)
    if analysis.get("variants"):
        document.add_heading("Рекомендации", 1)
    for variant in analysis.get("variants") or []:
        document.add_paragraph(variant.get("title") or "", style="Heading 2")
        document.add_paragraph(variant.get("details") or "").paragraph_format.keep_with_next = True
        document.add_paragraph(variant.get("rationale") or "")
    document.add_heading("Материалы и воспроизводимость", 1)
    for material in snapshot.get("materials", []):
        document.add_paragraph(material["filename"], style="Heading 2")
        document.add_paragraph("SHA-256 извлечённого текста: " + material["text_sha256"])
        document.add_paragraph(
            "SHA-256 оригинала: " + (material.get("original_sha256") or "не установлен")
        )
        document.add_paragraph(
            "Статус чтения: "
            + {
                "ok": "прочитан",
                "partial": "прочитан частично",
                "empty": "текст отсутствует",
                "error": "ошибка чтения",
            }.get(material.get("extraction_status"), "неизвестен")
        )
    document.add_paragraph("Версия движка: " + str(analysis.get("engine_version") or "неизвестна"))
    provenance = analysis.get("provenance") or {}
    llm = provenance.get("llm") or {}
    _model_receipts(document, llm)
    if provenance.get("window_readings"):
        document.add_heading("Происхождение чтений фрагментов", 2)
    for item in provenance.get("window_readings", []):
        document.add_paragraph("SHA-256 фрагмента: " + item["input_hash"])
        document.add_paragraph("Версия промпта: " + item["prompt_version"])
        document.add_paragraph(
            "Использовано сохранённое чтение."
            if item.get("cache_hit")
            else "Чтение выполнено при этом анализе."
        )
        original = item.get("provenance")
        if original is None:
            document.add_paragraph("Происхождение чтения неизвестно.")
        else:
            _model_receipts(document, original.get("llm") or {})
    for statute in provenance.get("statutes", []):
        document.add_paragraph(
            f"Норма: {statute.get('provision_locator')}; "
            f"редакция: {statute.get('edition_label')}; "
            f"проверка: {statute.get('verification_status')}"
        )
        document.add_paragraph("Источник нормы: " + str(statute.get("source_url") or "неизвестен"))
        document.add_paragraph(
            "SHA-256 редакции: " + str(statute.get("source_sha256") or "неизвестен")
        )
    for limitation in snapshot.get("limitations", []):
        document.add_paragraph("Ограничение: " + limitation)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


class DocxReportExporter:
    async def render(self, snapshot, version, created_at):
        return await asyncio.to_thread(build_report_docx, snapshot, version, created_at)
