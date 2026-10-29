"""Real Chromium + API acceptance; isolated CI database and synthetic accounts only."""

import asyncio
import os
import secrets
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
URL = "http://127.0.0.1:5179"


def prepare_database(password):
    from alembic import command
    from alembic.config import Config

    from src.config import settings

    if os.environ.get("CI") != "true" or settings.POSTGRES_HOST != "postgres":
        raise RuntimeError("Browser acceptance requires the isolated CI postgres service")
    if settings.POSTGRES_DB != "judgeai_browser_test":
        raise RuntimeError("Refusing to modify a non-acceptance database")

    async def create():
        import asyncpg

        connection = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database="postgres",
        )
        try:
            await connection.execute('DROP DATABASE IF EXISTS "judgeai_browser_test"')
            await connection.execute('CREATE DATABASE "judgeai_browser_test"')
        finally:
            await connection.close()

    async def seed():
        from src.db.auth import User
        from src.db.session import async_session_factory
        from src.services.auth import hash_password

        async with async_session_factory() as db:
            encoded = await hash_password(password)
            db.add_all(
                [User(username=name, password_hash=encoded) for name in ("browser-a", "browser-b")]
            )
            await db.commit()

    asyncio.run(create())
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    asyncio.run(seed())


def wait_for(url, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("Acceptance server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError("Acceptance server startup timed out")


class BrowserAuthAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        prepare_database(cls.password)
        cls.processes = []
        cls.addClassCleanup(cls.stop_servers)
        for command, cwd, url in [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                ],
                ROOT,
                "http://127.0.0.1:8011/health",
            ),
            (
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5179",
                    "--strictPort",
                ],
                ROOT / "verdikt-web",
                URL,
            ),
        ]:
            environment = {**os.environ, "API_PROXY_TARGET": "http://127.0.0.1:8011"}
            process = subprocess.Popen(command, cwd=cwd, env=environment)
            cls.processes.append(process)
            wait_for(url, process)
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch()
        cls.addClassCleanup(cls.browser.close)
        (ROOT / "acceptance-screenshots").mkdir(exist_ok=True)

    @classmethod
    def stop_servers(cls):
        for process in reversed(cls.processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def sign_in(self, page, username="browser-a"):
        page.get_by_label("Имя пользователя", exact=True).fill(username)
        page.get_by_label("Пароль", exact=True).fill(self.password)
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(page.locator(".cab")).to_be_visible()

    def account_action(self, page, label):
        if not page.get_by_role("button", name="Аккаунт", exact=True).is_visible():
            page.get_by_role("button", name="Открыть боковое меню", exact=True).click()
        page.get_by_role("button", name="Аккаунт", exact=True).click()
        page.get_by_role("menuitem", name=label, exact=True).click()

    def test_chat_navigation_pin_and_account_menu(self):
        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                self.sign_in(page)
                session = context.request.get(URL + "/api/auth/me").json()
                title = f"Закрепить тест {label}"
                response = context.request.post(
                    URL + "/api/chats",
                    data={"title": title},
                    headers={"X-CSRF-Token": session["csrf_token"]},
                )
                self.assertEqual(response.status, 201)
                page.reload()
                expect(page.locator(".cab-header").get_by_text("Выйти", exact=True)).to_have_count(
                    0
                )
                expect(
                    page.locator(".cab-header").get_by_text("Экспорт в DOCX", exact=False)
                ).to_have_count(0)
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню", exact=True).click()
                page.get_by_role("button", name="Свернуть боковое меню", exact=True).click()
                expect(page.get_by_label("Дела", exact=True)).not_to_be_visible()
                page.get_by_role("button", name="Открыть боковое меню", exact=True).click()
                expect(page.get_by_label("Дела", exact=True)).to_be_visible()
                trigger = page.get_by_role("button", name=f"Действия чата «{title}»", exact=True)
                trigger.click()
                expect(page.get_by_role("menuitem", name="Закрепить", exact=True)).to_be_focused()
                page.locator(".cab-list").evaluate("el => el.dispatchEvent(new Event('scroll'))")
                expect(page.get_by_role("menuitem", name="Закрепить", exact=True)).to_be_visible()
                page.keyboard.press("Escape")
                expect(trigger).to_be_focused()
                trigger.click()
                page.get_by_role("menuitem", name="Закрепить", exact=True).click()
                expect(page.get_by_text("Закреплённые", exact=True)).to_be_visible()
                expect(trigger).to_be_focused()
                page.reload()
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню", exact=True).click()
                expect(page.get_by_text("Закреплённые", exact=True)).to_be_visible()
                page.get_by_role("button", name=f"Действия чата «{title}»", exact=True).click()
                page.get_by_role("menuitem", name="Открепить", exact=True).click()
                expect(page.get_by_text("Закреплённые", exact=True)).to_have_count(0)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-chat-navigation.png"),
                    full_page=True,
                )
                self.account_action(page, "Настройки аккаунта")
                expect(
                    page.get_by_role("heading", name="Настройки аккаунта", exact=True)
                ).to_be_visible()
                context.close()

    def test_document_panel_and_full_conversation(self):
        from tests_pdf.fixtures import pdf
        from tests_unit.test_word_conversion import document

        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                self.sign_in(page)
                page.locator('input[type="file"]').last.set_input_files(
                    [
                        {
                            "name": "Synthetic verdict.pdf",
                            "mimeType": "application/pdf",
                            "buffer": pdf(pages=2),
                        },
                        {
                            "name": "Word judgment.docx",
                            "mimeType": "application/octet-stream",
                            "buffer": document(),
                        },
                    ]
                )
                page.get_by_role("button", name="Открыть Synthetic verdict.pdf", exact=True).click()
                expect(
                    page.locator('.document-panel canvas[data-rendered="true"]').first
                ).to_be_visible()
                page.get_by_role("button", name="Закрыть документ", exact=True).click()
                page.get_by_role("textbox", name="Задача по делу", exact=True).fill(
                    "Synthetic first question"
                )
                page.get_by_role("button", name="Отправить", exact=True).click()
                expect(page.locator(".result")).to_have_count(1, timeout=20000)
                page.get_by_role("textbox", name="Задача по делу", exact=True).fill(
                    "Synthetic follow-up question"
                )
                page.get_by_role("button", name="Отправить", exact=True).click()
                expect(page.locator(".result")).to_have_count(2, timeout=20000)
                expect(page.locator("[data-message-id]")).to_have_count(4)
                page.reload()
                expect(page.locator("[data-message-id]")).to_have_count(4)
                expect(page.get_by_text("Synthetic first question", exact=True)).to_be_visible()
                page.get_by_role("button", name="Открыть Synthetic verdict.pdf", exact=True).click()
                expect(
                    page.locator('.document-panel canvas[data-rendered="true"]').first
                ).to_be_visible()
                expect(page.get_by_role("button", name="Следующая", exact=True)).to_have_count(0)
                page.locator('[data-pdf-page="2"]').scroll_into_view_if_needed()
                expect(
                    page.locator('[data-pdf-page="2"] canvas[data-rendered="true"]')
                ).to_be_visible()
                self.assertGreater(page.locator(".pdf-pages").evaluate("(el) => el.scrollTop"), 0)
                page.locator('[data-pdf-page="1"]').scroll_into_view_if_needed()
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-document-panel.png"),
                    full_page=True,
                )
                page.get_by_role("button", name="Закрыть документ", exact=True).click()
                # The worker has its own real offline pagination gate. Stub only its
                # asynchronous HTTP status here to verify UI loading/failure/retry.
                polls = [0]

                def word_job(route):
                    route.fulfill(
                        json={
                            "id": "synthetic-word",
                            "filename": "Word judgment.docx",
                            "status": "queued",
                            "error": None,
                        }
                    )

                def word_status(route, _request, counter=polls):
                    counter[0] += 1
                    route.fulfill(
                        json={
                            "id": "synthetic-word",
                            "filename": "Word judgment.docx",
                            "status": "converting" if counter[0] == 1 else "failed",
                            "error": None if counter[0] == 1 else "Synthetic conversion failure",
                        }
                    )

                page.route("**/attachments/*/preview", word_job)
                page.route("**/api/document-previews/synthetic-word", word_status)
                page.get_by_role("button", name="Открыть Word judgment.docx", exact=True).click()
                expect(page.get_by_text("Подготавливаем документ", exact=True)).to_be_visible()
                expect(page.get_by_text("Synthetic conversion failure", exact=True)).to_be_visible(
                    timeout=10000
                )
                expect(page.get_by_role("link", name="Скачать", exact=True)).to_be_visible()
                page.get_by_role("button", name="Повторить", exact=True).click()
                expect(page.get_by_text("Synthetic conversion failure", exact=True)).to_be_visible()
                page.get_by_role("button", name="Закрыть документ", exact=True).focus()
                page.keyboard.press("Escape")
                expect(page.locator(".document-panel")).to_have_count(0)
                expect(
                    page.get_by_role("button", name="Открыть Word judgment.docx", exact=True)
                ).to_be_focused()

    def test_delete_chat_from_sidebar_cancel_error_confirm_and_reload(self):
        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                self.sign_in(page)
                session = context.request.get(URL + "/api/auth/me").json()
                title = f"Удалить тестовый чат {label}"
                response = context.request.post(
                    URL + "/api/chats",
                    data={"title": title},
                    headers={"X-CSRF-Token": session["csrf_token"]},
                )
                self.assertEqual(response.status, 201)
                chat_id = response.json()["id"]
                page.reload()
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню").click()
                page.get_by_label("Список дел").locator(".cab-row").filter(has_text=title).click()
                expect(page).to_have_url(URL + f"/app/case/{chat_id}/result")
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню").click()
                page.get_by_placeholder("Поиск по чатам").fill(title)
                remove = page.get_by_role("button", name=f"Действия чата «{title}»", exact=True)
                expect(remove).to_be_enabled()
                self.assertEqual(remove.locator("button").count(), 0)
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-delete-chat.png"),
                    full_page=True,
                )
                modal = page.get_by_role("dialog", name="Удалить чат?")
                remove.click()
                page.get_by_role("menuitem", name="Удалить чат", exact=True).click()
                expect(modal).to_be_visible()
                expect(modal.get_by_role("button", name="Отмена", exact=True)).to_be_focused()
                page.keyboard.press("Shift+Tab")
                page.keyboard.press("Shift+Tab")
                self.assertTrue(page.evaluate("!!document.activeElement.closest('dialog')"))
                page.keyboard.press("Tab")
                expect(modal.get_by_role("button", name="Закрыть окно", exact=True)).to_be_focused()
                page.keyboard.press("Escape")
                expect(modal).to_have_count(0)
                expect(remove).to_be_focused()
                remove.click()
                page.get_by_role("menuitem", name="Удалить чат", exact=True).click()
                modal.get_by_role("button", name="Отмена", exact=True).click()
                expect(modal).to_have_count(0)
                self.assertEqual(context.request.get(URL + f"/api/chats/{chat_id}").status, 200)
                remove.click()
                page.get_by_role("menuitem", name="Удалить чат", exact=True).click()
                expect(modal.get_by_text(title, exact=True)).to_be_visible()
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-delete-dialog.png"),
                    full_page=True,
                )
                endpoint = "**/api/chats/" + str(chat_id)
                page.route(
                    endpoint,
                    lambda route: (
                        route.fulfill(status=409, json={"detail": "Тестовая ошибка удаления"})
                        if route.request.method == "DELETE"
                        else route.continue_()
                    ),
                )
                confirm = modal.get_by_role("button", name="Удалить чат", exact=True)
                confirm.click()
                expect(modal.get_by_role("alert")).to_contain_text("Тестовая ошибка удаления")
                expect(confirm).to_be_enabled()
                page.unroute(endpoint)
                held = []
                page.route(
                    endpoint,
                    lambda route, request, held=held: (
                        held.append(route)
                        if route.request.method == "DELETE"
                        else route.continue_()
                    ),
                )
                confirm.click()
                expect(modal.get_by_role("status")).to_have_text("Удаляем чат…")
                expect(modal.get_by_role("button", name="Отмена", exact=True)).to_be_disabled()
                expect(
                    modal.get_by_role("button", name="Закрыть окно", exact=True)
                ).to_be_disabled()
                page.keyboard.press("Escape")
                expect(modal).to_be_visible()
                self.assertEqual(len(held), 1)
                held[0].fulfill(response=held[0].fetch())
                page.unroute(endpoint)
                expect(modal).to_have_count(0)
                expect(page).to_have_url(URL + "/app")
                expect(remove).to_have_count(0)
                self.assertEqual(context.request.get(URL + f"/api/chats/{chat_id}").status, 404)
                page.reload()
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню").click()
                expect(
                    page.get_by_role("button", name=f"Действия чата «{title}»", exact=True)
                ).to_have_count(0)
                context.close()

    def test_account_profile_search_and_settings_at_both_widths(self):
        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                self.sign_in(page)
                if label == "mobile":
                    page.get_by_role("button", name="Открыть боковое меню").click()
                page.get_by_placeholder("Поиск по чатам").fill("synthetic-no-match-42")
                expect(
                    page.get_by_text("Ничего не найдено. Попробуйте другой запрос.")
                ).to_be_visible()
                page.get_by_role("button", name="Сбросить поиск").click()
                self.account_action(page, "Настройки аккаунта")
                expect(page.get_by_role("heading", name="Настройки аккаунта")).to_be_visible()
                page.get_by_label("Имя", exact=True).fill("Тест")
                page.get_by_label("Фамилия", exact=True).fill("Профиль")
                page.get_by_role("button", name="Сохранить профиль").click()
                expect(page.get_by_role("status")).to_contain_text("Профиль сохранён")
                page.reload()
                expect(page.get_by_label("Имя", exact=True)).to_have_value("Тест")
                for tab, suffix in [
                    ("Профиль", "profile"),
                    ("Безопасность", "security"),
                    ("Данные", "data"),
                ]:
                    page.get_by_role("tab", name=tab, exact=True).click()
                    self.assertLessEqual(
                        page.evaluate("document.documentElement.scrollWidth"), width
                    )
                    if suffix == "security":
                        expect(page.get_by_text("Этот сеанс", exact=True)).to_be_visible()
                    if suffix == "data":
                        # The JSON export was removed from the profile at the owner's request.
                        expect(page.get_by_role("button", name="Скачать данные")).to_have_count(0)
                        expect(page.get_by_role("button", name="Удалить дела")).to_be_visible()
                    page.screenshot(
                        path=str(ROOT / "acceptance-screenshots" / f"{label}-{suffix}.png"),
                        full_page=True,
                    )
                context.close()

    def test_real_login_errors_reload_logout_expiry_and_private_access(self):
        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                expect(page.get_by_label("Имя пользователя", exact=True)).to_be_visible()
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-login.png"), full_page=True
                )
                page.get_by_label("Имя пользователя", exact=True).fill("browser-a")
                page.get_by_label("Пароль", exact=True).fill("deliberately-invalid")
                page.get_by_role("button", name="Войти", exact=True).click()
                expect(page.get_by_role("alert")).to_contain_text(
                    "Неверное имя пользователя или пароль"
                )
                self.sign_in(page)
                cookie = next(c for c in context.cookies() if c["name"] == "judgeai_session")
                self.assertTrue(cookie["httpOnly"])
                self.assertEqual(cookie["sameSite"], "Strict")
                self.assertNotIn("judgeai_session", page.evaluate("document.cookie"))
                self.assertEqual(
                    page.evaluate(
                        "Object.keys(localStorage).filter(k => /session|token|password/i.test(k))"
                    ),
                    [],
                )
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-workspace.png"),
                    full_page=True,
                )
                page.locator('input[type="file"]').last.set_input_files(
                    {"name": "synthetic-empty.txt", "mimeType": "text/plain", "buffer": b" "}
                )
                expect(page.get_by_text("Загружен · ожидает чтения", exact=True)).to_be_visible()
                page.get_by_role("button", name="Отправить", exact=True).click()
                expect(page.get_by_text("Текст не найден", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_role("alert")).to_contain_text("Читаемый текст не найден")
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-reading-failure.png"),
                    full_page=True,
                )
                page.reload()
                expect(page.locator(".cab")).to_be_visible()
                session = context.request.get(URL + "/api/auth/me").json()
                self.assertEqual(
                    context.request.post(
                        URL + "/api/chats", data={"title": "Synthetic acceptance"}
                    ).status,
                    403,
                )
                response = context.request.post(
                    URL + "/api/chats",
                    data={"title": "Synthetic acceptance"},
                    headers={"X-CSRF-Token": session["csrf_token"]},
                )
                self.assertEqual(response.status, 201)
                chat_id = response.json()["id"]
                other = self.browser.new_context()
                self.addCleanup(other.close)
                other_page = other.new_page()
                other_page.goto(URL + "/app")
                self.sign_in(other_page, "browser-b")
                self.assertEqual(
                    other.request.get(URL + f"/api/chats/{chat_id}/messages").status, 404
                )
                self.account_action(page, "Выйти")
                expect(page.get_by_label("Имя пользователя", exact=True)).to_be_visible()
                self.assertEqual(context.request.get(URL + "/api/chats").status, 401)
                self.sign_in(page)

                async def expire():
                    from sqlalchemy import update

                    from src.db.auth import UserSession
                    from src.db.session import async_session_factory

                    async with async_session_factory() as db:
                        await db.execute(
                            update(UserSession).values(
                                expires_at=datetime.now(UTC) - timedelta(seconds=1)
                            )
                        )
                        await db.commit()

                # Playwright sync owns an event loop on this thread.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(lambda: asyncio.run(expire())).result(timeout=20)
                page.reload()
                expect(page.get_by_label("Имя пользователя", exact=True)).to_be_visible()
                self.assertEqual(context.request.get(URL + "/api/chats").status, 401)
                context.close()

    def test_open_registration_signs_in_and_survives_relogin(self):
        for width, height, label in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
            with self.subTest(viewport=label):
                context = self.browser.new_context(viewport={"width": width, "height": height})
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(URL + "/app")
                page.get_by_role("button", name="Зарегистрироваться", exact=True).click()
                expect(page.get_by_role("heading", name="Регистрация")).to_be_visible()
                username = f"new-judge-{label}"
                page.get_by_label("Имя пользователя", exact=True).fill(username)
                page.get_by_label("Пароль", exact=True).fill("short")
                page.get_by_role("button", name="Зарегистрироваться", exact=True).first.click()
                # The browser blocks a password under 12 characters before any request.
                self.assertEqual(
                    page.locator("#password").evaluate("el => el.validity.tooShort"), True
                )
                page.get_by_label("Пароль", exact=True).fill(self.password)
                page.screenshot(
                    path=str(ROOT / "acceptance-screenshots" / f"{label}-register.png"),
                    full_page=True,
                )
                page.locator("form").get_by_role("button", name="Зарегистрироваться").click()
                expect(page.locator(".cab")).to_be_visible()
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                self.account_action(page, "Выйти")
                expect(page.get_by_label("Имя пользователя", exact=True)).to_be_visible()
                self.sign_in(page, username)
                context.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
