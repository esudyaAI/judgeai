"""Account operations through a narrow persistence port; no HTTP or SQL imports."""

from typing import Protocol


class AccountError(Exception):
    pass


class AnalysisInProgress(Exception):
    pass


class AccountRepository(Protocol):
    async def export_data(self, user_id: int, profile: dict) -> dict: ...
    async def delete_cases(self, user_id: int) -> dict: ...
    async def read_profile(self, user_id: int) -> dict: ...
    async def write_profile(self, user_id: int, profile: dict) -> None: ...
    async def password_hash(self, user_id: int) -> str | None: ...
    async def replace_password(self, user_id: int, encoded: str, current_token: str) -> None: ...
    async def sessions(self, user_id: int, current_token: str) -> list[dict]: ...
    async def revoke_session(self, user_id: int, current_token: str, session_id: str) -> bool: ...


class AccountUseCases:
    def __init__(self, repository: AccountRepository, verify_password, hash_password):
        self.repository = repository
        self.verify_password = verify_password
        self.hash_password = hash_password

    async def profile(self, user_id: int) -> dict:
        return await self.repository.read_profile(user_id)

    async def save_profile(self, user_id: int, profile: dict) -> dict:
        await self.repository.write_profile(user_id, profile)
        return profile

    async def change_password(self, user_id: int, old: str, new: str, token: str) -> None:
        if not await self.verify_password(await self.repository.password_hash(user_id), old):
            raise AccountError("Текущий пароль неверен")
        encoded = await self.hash_password(new)
        await self.repository.replace_password(user_id, encoded, token)

    async def export_data(self, user_id: int) -> dict:
        return await self.repository.export_data(
            user_id, await self.repository.read_profile(user_id)
        )

    async def delete_cases(self, user_id: int, password: str, confirmation: str) -> dict:
        if confirmation != "УДАЛИТЬ":
            raise AccountError("Введите УДАЛИТЬ для подтверждения")
        if not await self.verify_password(await self.repository.password_hash(user_id), password):
            raise AccountError("Пароль неверен")
        return await self.repository.delete_cases(user_id)

    async def sessions(self, user_id: int, token: str) -> list[dict]:
        return await self.repository.sessions(user_id, token)

    async def revoke(self, user_id: int, token: str, session_id: str) -> bool:
        return await self.repository.revoke_session(user_id, token, session_id)
