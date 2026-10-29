# Покрытие состояний интерфейса

Основа аудита: main d728099, 29.10.2026. Это проект доработки, не подтверждение готового покрытия. Статусы выполнения — только в docs/TASKS.md.

## Цель и выбранный подход

Сохранить привычный рабочий чат судебного помощника, текущую композицию, цвета и русский интерфейс. Сделать ожидание, ошибку, недоступность действия и результат однозначными; обеспечить клавиатуру, мобильный экран и уменьшенное движение.

Рассмотрены CSS без зависимостей и Framer Motion. Пользователь выбрал Framer Motion. Использовать официальный пакет Motion for React (motion/react), одну фиксированную версию в lockfile, общие настройки spring и reducedMotion=user. GSAP одновременно не нужен. Без изменения бизнес-правил, API/БД, статусов прочитанности и функций анализа.

Визуальная основа: существующий Onest для текста/заголовков, tabular-nums для времени; ink #141414, background #ffffff, surface #f3f3f3, muted #707070, focus #0066ff, warning #b54708. Уже существующие цвета ошибок сохраняются. Небольшая пружина на нажатии и появлении; без декоративного движения длинных результатов/PDF-страниц.

## Правило Zero-Overlook

Для каждой группы интерактивных элементов: default, hover на устройствах с указателем, pressed, pending, disabled, focus-visible, клавиатура и touch. Pending/disabled применяются по реальному смыслу: обычная навигационная ссылка не получает фиктивную загрузку. Для неприменимого состояния записывать причину. Для сетевого действия — lock от повторов, видимая локальная обратная связь, доступный статус, ошибка и retry. Блокированная кнопка не меняется при hover/pressed. Фокус и смысл не зависят от анимации.

## Карта поверхностей и подтверждённые пробелы исходного кода

| Поверхность / элементы | Что уже есть | Что проверить / доработать |
|---|---|---|
| Лендинг: навигация, CTA, footer | Ссылки и текущие переходы | Общие focus/pressed; pending и disabled неприменимы обычным ссылкам |
| FAQ | expanded, сворачивание, CSS переход | Клавиатура, reduced-motion, отсутствие фокуса в закрытом содержимом |
| Информационные страницы | Контент, навигация, current | Общий focus, мобильные длинные ссылки |
| Вход / регистрация | Проверка сеанса, ошибка связи/retry, pending/error submit | Пустые/невалидные поля пока не блокируют submit; явная pending-индикация; ошибки валидации по-русски |
| Сеанс истёк / выход | 401 возвращает вход; logout в меню аккаунта | Локальный pending logout и защита от повторов; ошибка выхода |
| Список дел | Ошибка/retry; список | Нет первого loading/empty; retry без локального pending; stale запрос не должен стирать свежий результат |
| Поиск | Debounce, abort, pending, empty, error/retry/reset | Desktop/mobile + длинная строка, отсутствие результатов после удаления |
| Меню чата / аккаунта | Клавиатурные стрелки, Escape/outside, возврат фокуса | Появление/закрытие, недоступные действия не реагируют на hover, связь trigger/menu |
| Закрепление | Lock, disabled, error | Нет видимого локального pending после закрытия меню |
| Удаление чата | Native dialog, cancel/focus, pending/error/success | Motion и reduced-motion; существующие блокировки/фокус не ухудшать |
| Боковая панель | Desktop collapse, mobile drawer, Escape | На mobile фон не inert и фокус не удерживается; вернуть фокус на открывающий элемент; учитывать меню в portal |
| Новое дело / подсказки | Dropzone, drag, предложения | Подсказки сейчас все вызывают один onFiles(null), выбранная задача не попадает в composer |
| Вложения до отправки | Выбрать, открыть, убрать | Повторный выбор того же файла; длинные/одинаковые имена; действия при отправке |
| Отправка / composer | Disabled пустого ввода, lock, фон вместо отмены | Различить отправку и уже запущенный анализ; локальный pending; убрать изменения вложений во время отправки |
| История дела | Загрузка, ошибка, пустой чат, история | Доступная загрузка/повтор; 404 без выдуманного результата |
| Анализ | Pending/running, стадии, shimmer, timer, failed, completed | Сохранить один индикатор; не добавлять дублирующую загрузку сверху |
| Результат | Частичные данные, warnings, legal checks | Пустой список смягчающих сейчас оставляет пустую карточку; unknown не называть отсутствием; варианты/раскрытие/длинный текст |
| Приговоры практики | Открываемый приговор / строка без текста | Loading/error текста, доступ к источнику и download, отсутствие практики — existing source note |
| Панель PDF/Word/TXT | Word queue/converting/failure/retry, original download | Motion enter/exit, фокус; timeout Word содержит английский текст; для TXT/MD iframe нет явного loading/error и MD ошибочно идёт в PDF |
| PDF | Document/page loading, password/timeout/corrupt/limit/retry | Регресс обычной прокрутки, отдельная ошибка страницы, desktop/mobile, выделение текста |
| Профиль | Loading/error/reload, save/error/success, avatar guards | Общий busy без идентификации действия; во время busy вкладки позволяют потерять сообщение; явный pending; email invalid |
| Безопасность | Password mismatch, смена пароля, sessions/revoke | Disabled незаполненных форм; pending для конкретного действия; empty sessions; tab arrow/Home/End navigation |
| Данные | Явное подтверждение удаления, пароль, ошибки API | Пароль не участвует в disabled; pending удаления; существующие гарантии без изменений |

## Реализация

1. Общие presentation-компоненты статуса/кнопки ожидания и настройки Motion. Не переносить бизнес-логику в визуальные компоненты.
2. Сначала регрессионные проверки подтверждённых пробелов, затем исправления форм, списка/операций, composer/подсказок, текстового просмотра.
3. Управление фокусом и inert фона мобильного drawer с сохранением portal menu; tablist roving focus. Не задерживать снятие блокировок/отмену сетевых запросов ради exit-анимации.
4. Короткие spring enter/exit меню/диалогов/документа, смена вкладок, pressed controls. Reduced-motion без transform; exits не должны оставлять фокусируемые невидимые элементы. Существующие landing-анимации не переписывать целиком.
5. Реестр всех элементов/состояний и автоматизированные сценарии на синтетических API-ответах; общий браузерный регресс существующих функций.

## Проверки / Definition of Done

- Все строки карты разобраны; для каждого реального интерактивного элемента записан механизм пяти состояний или обоснованный N/A, плюс keyboard/focus.
- Build/typecheck/unit проходят, новые browser behavior tests проверяют pending/error/retry и отрицательные сценарии.
- Desktop1440×1000/mobile390×844: формы, пустой/ошибочный список, меню, drawer, удаление, отправка, анализ, настройки, preview. Скриншоты просмотрены, overflow/console проверены.
- Reduced-motion проверен в реальном браузере; анимации не влияют на API/доступность. Зависимость и её лицензия отражены в inventory.
- Независимое review; обязательный CI при публикации. Не заявлять покрытие всех состояний по одному успешному screenshot.
- Все результаты/провалы/непроверенное отражены в docs/TASKS.md. Merge/deploy отдельно.

## Риски и границы

- Exit-анимации могут удержать dialog/inert/фокус после закрытия: покрыть быстрым закрытием/повторным открытием и сменой маршрута.
- PDF ленивый; Motion не должен сместить canvas/text layer или сломать lazy загрузку.
- Состояния сетевого слоя проверять искусственными задержками и отказами, без персональных материалов.
- Неработающий download проекта приговора остаётся честно disabled с объяснением: эта задача не создаёт backend экспорта.
- Статусы unread/seen — отдельная незавершённая работа в другом checkout, сюда не смешивать.

Первичные документы Motion: https://motion.dev/docs/react-installation , https://motion.dev/docs/react-motion-config , https://motion.dev/docs/react-animate-presence .

## Дополнение независимой проверки проекта

- Пересечения mobile drawer/portal menu/delete dialog/document panel: Escape закрывает верхний слой, фокус остаётся в нём; resize во время открытия.
- Исчезающий слой сразу исключается из pointer/keyboard; фокус восстанавливается до завершения spring.
- Смена/закрытие документа при загрузке: поздний ответ не заменяет новый документ или его статус. TXT iframe требует отдельной проверки Escape/выхода из frame; предпочтительно контролируемый текстовый viewer с loading/error.
- Офлайн/обрыв ответа мутации: не повторять отправку/удаление автоматически без серверной идемпотентности.
- Изменение reduced-motion во время работы; длинные русские названия, масштаб200%, мобильная клавиатура composer.

## Контракт пяти состояний по элементам

Это постоянный checklist для последующих UI изменений; результаты конкретного прогона хранятся в TASKS.md. D/H/P/L/X = обычное/наведение/нажатие/ожидание/блокировка. Focus обязателен в каждой строке. N/A не является пропущенным тестом: состояние не имеет смысла для мгновенного действия.

| Элементы | D/H/P | L | X | Дополнительные состояния |
|---|---|---|---|---|
| Link/a лендинга, информационных страниц, privacy/source/download | Общие link/btn правила | N/A: переход/скачивание браузера, без собственной задачи | N/A: существуют только доступные ссылки; недоступный export — отдельная disabled кнопка | focus, external rel, current route |
| FAQ | expanded button, hover, pressed | N/A: локальное раскрытие | N/A: всегда можно раскрыть | collapsed/expanded/reduced motion |
| Вход/регистрация submit | BusyButton | pending label/spinner/aria-busy | pending либо невалидные обязательные поля | connection error/401/conflict/success; secret cleared |
| Переключение вход/регистрация | auth-switch | N/A: локальная смена | pending запроса | hint/error reset |
| Все поля auth/profile/password/confirmation/search/composer | native field/focus/hover | N/A: ввод не отправляет мутацию; поиск показывает pending в списке | busy соответствующей формы; search остаётся доступен для отмены debounce | empty/invalid/max length/autofill |
| Retry связи/списка/истории/settings/PDF/текста | btn/BusyButton | соответствующий loading экран вместо прежней кнопки либо BusyButton | pending; старый запрос отменён/игнорируется | retained error, next attempt |
| Новое дело, подсказка, attach/dropzone, сброс поиска | btn/Pressable/dropzone | N/A: локальная подготовка | attach disabled во время send/analysis | drag/drop/cancel picker/same-file reselect |
| Выбрать чат, открыть/свернуть sidebar, открыть меню | row/btn/glyph-only dots | N/A: локальная навигация; история показывает собственный loading | N/A: работают во время анализа другого дела | one shared chat row, current, keyboard, scrim |
| Пункт закрепить/открепить | menu item | локальный status до завершения API+refresh | общий pin lock | error, changed group, persisted after reload |
| Пункт удалить чат | menu item | N/A: открывает подтверждение | активный analysis/deletion | dialog follows |
| Dialog delete: отмена/крестик/подтвердить | native dialog + btn/BusyButton | confirm pending; status | все закрытия и повторное подтверждение при pending | error/success/files_pending, focus trap |
| Аккаунт: настройки/выход | menu item | локальный logout status | logout lock | network failure stays signed in |
| Send | BusyButton icon | pending send, затем отдельный analysis | empty input + no files, pending, analysis | retained draft/attachments on failure, no auto-retry |
| Продолжить в фоне | btn | N/A: только скрывает текущий ход анализа | N/A: это не отмена серверной работы | новая страница/история продолжается |
| Открыть/убрать вложение | filename/button | document viewer owns loading | убрать disabled во время отправки, открыть disabled если handler отсутствует | same names removed by index, long names |
| Similar verdict/show all/variants | row/button, current selection | viewer owns loading; local expand/variant N/A | verdict without id shown as text, no false button | zero/partial practice, many results |
| Close/download document | btn/link | N/A: закрытие и browser download | N/A: оригинал доступен даже при failed preview | mobile modal, resize, interrupted preview, return opener |
| Фото изменить/убрать | BusyButton/btn | read avatar pending | account busy; remove only when avatar exists | format/size/read errors, explicit save |
| Сохранить профиль/отмена | BusyButton/btn | named save pending | account busy; optional empty profile permitted | saved/error/invalid email |
| Вкладки settings | seg + roving focus | N/A: локальная смена | account busy | arrows/Home/End, panel exit inert |
| Изменить пароль | BusyButton | named password pending | missing/short/mismatch/busy | sessions refreshed after success |
| Завершить сеанс/выйти из текущего | BusyButton | named session pending | account busy | empty sessions/error/current distinction |
| Удалить все дела/отмена/подтверждение | btn/BusyButton | named deletion pending | missing password/incorrect УДАЛИТЬ/busy | server conflict while analysis, explicit irreversible confirmation |
| Скачать проект приговора (существующая заглушка) | btn | N/A: backend export отсутствует | всегда disabled с объяснением | не выдавать несуществующий документ |

Нативный dialog удаления закрывается сразу с восстановлением фокуса; spring применяется к его появлению. Удерживать невидимый modal до конца exit ради декорации небезопасно. Меню, вкладки и document panel имеют enter/exit, исчезающие слои сразу inert/aria-hidden. Текущий CSS-переход drawer сохранён, Motion применяется к связанным popup/menu/panel/tab/press. Новых загрузок над ходом анализа не добавлено.
