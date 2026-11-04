# Техническая точка сохранения — 04.11.2026

Работа подготовлена в ветке `work/analysis-review-checkpoint`; 04.11.2026 владелец разрешил интеграцию в основную `main` и push. Общая разработка приостановлена по просьбе владельца. Единственный актуальный реестр задач, проверок и оставшейся работы — [docs/TASKS.md](docs/TASKS.md); этот документ описывает состав и эксплуатацию сохранённого среза.

## Состав изменений

- Авторизованный SSE прогресс анализа с проверкой владельца и резервным REST polling.
- Чтение всех сегментов документов, хеши текстов и точные Unicode-координаты цитат: [контракт извлечения](docs/ANALYSIS_EXTRACTION.md).
- Контроль внешней обработки, локальная псевдонимизация и безопасные ошибки: [политика подключения](docs/EXTERNAL_PROCESSING.md). Эвристический детектор не является гарантией удаления любых персональных данных.
- Изолированный по владельцу/делу кэш чтений и исходные provider/model/prompt receipts: [миграционный план](docs/PRIVATE_WINDOW_CACHE_MIGRATION.md), [план происхождения чтений](docs/superpowers/plans/2026-11-04-window-provenance.md).
- Неизменяемые снимки расчёта и история машинных/человеческих версий. API исправлений проверяет исходную версию, типы, лицо, цитату, автора и повторный запрос; сохраняет результат атомарно: [контракт версий и исправлений](docs/ANALYSIS_REVISIONS.md).
- Повторный отбор практики из исходной сохранённой выборки конкретного осуждённого существующими фильтрами/расчётами. Новые и ранее исключённые корпусом карточки не добавляются автоматически; стадия и временная применимость норм не объявляются сверенными этим сравнением.
- Сохранённые DOCX, история отчётов в интерфейсе и скачивание исходных байтов без пересчёта. Журнал исправлений, ограничения, статистика и подписи неизвестных фактов входят в новый отчёт: [план отчётов](docs/superpowers/plans/2026-11-04-case-reports.md).

Команды человеческой проверки доступны через API. Полноценный пользовательский редактор, интерфейс истории версий анализа/выбора цитат и экспорт произвольной выбранной версии анализа остаются отложенной работой T13/T14. История готовых отчётов и история версий анализа — разные функции. Экспертная правовая приёмка, политика внешней обработки и инфраструктурная/нагрузочная приёмка не подменяются техническими тестами.

## Конфигурация и данные

Новые миграции: `0013_private_window_cache`, `0014_case_reports`, `0015_window_provenance`, `0016_analysis_revisions`. Они проверяются на изолированных тестовых БД. Перед применением к рабочей БД нужны резервная копия и проверенный план восстановления из соответствующих документов; рабочие миграции в этой сессии не выполнялись. Старые записи не получают выдуманные inputs/reviewer/model metadata. Downgrade с непустыми приватными данными/metadata требует предварительного архива и не удаляет их молча.

Реальные внешние LLM/embedding endpoints по умолчанию закрыты до зафиксированного решения: `EXTERNAL_PROCESSING_APPROVAL_ID` и `EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS`. Значения и допустимые материалы согласуются владельцем; разрешение не создаётся автоматически. Для синтетической локальной проверки используется `LLM_PROVIDER=fake` вместе с `LLM_ALLOW_FAKE=true`. Runtime `.env`, реальные материалы, секреты, кэши и screenshots не входят в коммиты/release context.

## Воспроизведение проверок

Команды и окружения соответствуют [.github/workflows/ci.yml](.github/workflows/ci.yml):

```sh
# Отдельное окружение Python; обе части monorepo нужны вместе.
pip install '.[dev]' ./packages/legal_core

# Без сторонних зависимостей, как inventory job.
PYTHONPATH=.:packages/legal_core python -S -m unittest discover -s tests_unit -v
PYTHONPATH=.:packages/legal_core python -S tools/dependency_inventory.py --check

# Только выделенная тестовая PostgreSQL/pgvector БД с именем, оканчивающимся _test.
pytest tests tests_uploads tests_uploads_http tests_pdf tests_reading --cov=src
(cd packages/legal_core && pytest)
ruff check src tests packages/legal_core tests_browser tests_uploads tests_uploads_http tests_pdf tests_reading tests_unit tools
ruff format --check src tests packages/legal_core tests_browser tests_uploads tests_uploads_http tests_pdf tests_reading tests_unit tools

(cd verdikt-web && npm ci && npm test && npm run build)
```

Browser acceptance требует отдельного CI postgres, синтетических аккаунтов, Playwright Chromium и окружения из workflow. UI-state runner получает `PLAYWRIGHT_MODULE` из фактического расположения установленного Playwright, а не фиксированного номера Python. Word pagination/isolation проверяется реальным LibreOffice в network-none/read-only preview container.

Итоговые результаты текущего среза, версии среды и ссылки на коммиты фиксируются в завершающей записи [docs/TASKS.md](docs/TASKS.md). Проверки локально воспроизводят CI; удалённый GitHub Actions run появляется после публикации ветки. Push в `main` запускает сборку и production deploy, поэтому сохранение выполняется в отдельной локальной ветке.

## Проверенный срез

На этой точке выполнено локальное воспроизведение CI в свежем образе Python3.12.16:803 теста API/адаптеров, coverage89,68%;297 тестов legal_core, coverage97,69%; Ruff/check-format. Inventory job без сторонних зависимостей:107 тестов. Node22.23.4:109 unit tests, typecheck/build; Chromium:7 E2E и14 UI flows на desktop/mobile. API/web/preview images и оба Python wheel собраны; реальная offline Word conversion/isolation прошла. Пороги покрытия80% сохранены. Подробные даты, среды и исправленные неуспешные запуски — в едином реестре TASKS.

Реальные провайдеры и рабочая БД не активировались этими проверками. На момент исходного checkpoint remote CI/deploy не запускался; последующая публикация разрешена владельцем и учитывается в TASKS. Перед публикацией необходимы согласованные эксплуатационные условия из указанных документов.

## Коммиты

- `b793642` — backend: защищённое чтение, приватные кэши/receipts, immutable reports/revisions, typed human review и frozen practice refilter, миграции и тесты.
- `09cf270` — интерфейс: SSE/polling, отчёты/скачивание/история готовых отчётов, неизвестные факты и browser/frontend проверки.
- Завершающий `chore(ci)` commit этой ветки — Docker context, этот технический индекс, README и полный журнал проверок/паузы в TASKS.

Рабочие файлы и коммиты содержат исходники и синтетические тесты; runtime env, credentials, реальные дела, модели и screenshots исключены. Последующий статус разрешённой публикации и CI/deploy фиксируется в docs/TASKS.md.
