"""Account guards independent of HTTP, database and Argon2 runtime."""

import unittest
from unittest.mock import AsyncMock

from src.application.account import AccountError, AccountUseCases, AnalysisInProgress


class AccountUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = AsyncMock()
        self.verify = AsyncMock(return_value=True)
        self.hash = AsyncMock(return_value="encoded")
        self.actions = AccountUseCases(self.repo, self.verify, self.hash)

    async def test_wrong_password_has_no_write_or_revoke(self):
        self.verify.return_value = False
        with self.assertRaises(AccountError):
            await self.actions.change_password(1, "old", "new", "token")
        self.hash.assert_not_awaited()
        self.repo.replace_password.assert_not_awaited()

    async def test_password_hash_failure_does_not_replace_credentials(self):
        self.hash.side_effect = ValueError("invalid password")
        with self.assertRaises(ValueError):
            await self.actions.change_password(1, "old", "new", "token")
        self.repo.replace_password.assert_not_awaited()

    async def test_delete_requires_both_explicit_confirmation_and_valid_password(self):
        with self.assertRaises(AccountError):
            await self.actions.delete_cases(1, "password", "")
        self.repo.password_hash.assert_not_awaited()
        self.verify.return_value = False
        with self.assertRaises(AccountError):
            await self.actions.delete_cases(1, "password", "УДАЛИТЬ")
        self.repo.delete_cases.assert_not_awaited()

    async def test_active_analysis_error_propagates(self):
        self.repo.delete_cases.side_effect = AnalysisInProgress
        with self.assertRaises(AnalysisInProgress):
            await self.actions.delete_cases(1, "password", "УДАЛИТЬ")

    async def test_profile_storage_failure_cannot_report_success(self):
        self.repo.write_profile.side_effect = OSError("database unavailable")
        with self.assertRaises(OSError):
            await self.actions.save_profile(1, {"firstName": "Анна"})
