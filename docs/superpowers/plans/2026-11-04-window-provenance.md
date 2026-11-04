# Происхождение повторно используемых чтений окон — T14/T13

Статусы только в docs/TASKS.md. Прочитаны case-reports plan, punishment_window_resolver, guarded provider/fallback и обе cache-таблицы.

## Контракт

Новое чтение окна сохраняет вместе с результатом метаданные успешных вызовов именно этого окна: adapter/requested model, хеш системного промпта/инструкции приватности, хеш endpoint без самого URL, время; точная ревизия весов не выдумывается. Отдельные concurrent windows не получают receipts соседних вызовов. Отказы модели не кешируются; пустые/неподтверждённые чтения кешируются с происхождением, но не становятся подтверждёнными фактами.

resolve_windows сохраняет совместимый результат (window,term); optional audit collector возвращает input hash, prompt version, cache hit/miss, provenance или unknown для каждого окна. Runner сохраняет эти метаданные в CaseAnalysis.provenance.window_readings. Повторное использование копирует исходные метаданные, не текущие settings. DOCX явно показывает сохранённые сведения и unknown. Сами окна/PII/token mappings в metadata не добавляются. Коллектор receipts локален asyncio task через ContextVar и не меняет работу fallback/внешние payload.

## Миграция0015

Добавить nullable JSONB provenance в private_llm_window_extractions и llm_window_extractions. Value/ключи/чтения остаются прежними: предыдущий код игнорирует дополнительный столбец. Старые строки не backfill-ить текущими настройками: NULL означает unknown. Новые строки пишут результат и provenance одним INSERT/transaction; on-conflict сохраняет первоначальную запись. Другие данные/схемы не меняются.

Миграция сначала только в isolated test DB. Рабочее применение требует отдельного разрешения и backup/restore. Для rollback приложения SQL downgrade не нужен. Downgrade столбцов с непустым provenance отказывается до явного архивирования metadata; пустые/legacy NULL допустимы. Offline downgrade не может доказать пустоту и отказывается. Кешированные результаты/частные материалы никогда автоматически не удаляются.

## Проверки

TDD: cache miss/hit с теми же metadata после смены клиента; legacy NULL остаётся unknown; два concurrent окна с разными receipts не перемешаны; failed call не записывает cache; private owner-scoping/cascade прежние. Реальный MockTransport и fallback доказывают requested model/prompt hash без исходников/ключей/URL в metadata. API analysis→report→DOCX включает provenance окна и сохраняет old snapshot. Alembic metadata parity, пустой roundtrip и populated downgrade guard. Затем профиль и актуальная общая регрессия.

## Остаток T13

Подтверждение/исправление фактов требует отдельного сохранённого набора calculation inputs и новой версии результата; запрещено представлять правку вывода как пересчёт. Snapshot отчёта и исторические версии анализа неизменны. Утверждённая юристом матрица охвата/применимости норм и приёмка остаются отдельными требованиями.
