"""SQL persistence for private profiles, password changes and revocable sessions."""

import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from src.db.auth import User, UserProfile, UserSession
from src.infrastructure.account_data import delete_cases, export_cases
from src.services.auth_tokens import token_digest


def session_reference(current_token: str, target_hash: str) -> str:
    # Neither the bearer nor its DB hash is exposed as a session identifier.
    return hmac.new(current_token.encode(), target_hash.encode(), hashlib.sha256).hexdigest()


class SqlAccountRepository:
    def __init__(self, db):
        self.db = db

    async def read_profile(self, user_id):
        row = await self.db.get(UserProfile, user_id)
        return row.payload if row else {}

    async def write_profile(self, user_id, profile):
        await self.db.execute(
            insert(UserProfile)
            .values(user_id=user_id, payload=profile)
            .on_conflict_do_update(index_elements=[UserProfile.user_id], set_={"payload": profile})
        )
        await self.db.commit()

    async def password_hash(self, user_id):
        # Serialize password changes so two concurrent requests cannot both use the old password.
        user = await self.db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return user.password_hash

    async def replace_password(self, user_id, encoded, current_token):
        user = await self.db.get(User, user_id)
        user.password_hash = encoded
        await self.db.execute(
            delete(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.token_hash != token_digest(current_token),
            )
        )
        await self.db.commit()

    async def sessions(self, user_id, current_token):
        rows = (
            await self.db.scalars(
                select(UserSession)
                .where(UserSession.user_id == user_id, UserSession.expires_at > datetime.now(UTC))
                .order_by(UserSession.created_at.desc())
            )
        ).all()
        return [
            {
                "id": session_reference(current_token, row.token_hash),
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "current": row.token_hash == token_digest(current_token),
            }
            for row in rows
        ]

    async def revoke_session(self, user_id, current_token, session_id):
        rows = (
            await self.db.scalars(select(UserSession).where(UserSession.user_id == user_id))
        ).all()
        for row in rows:
            if hmac.compare_digest(session_reference(current_token, row.token_hash), session_id):
                if row.token_hash == token_digest(current_token):
                    return False  # current session uses the existing logout flow
                await self.db.delete(row)
                await self.db.commit()
                return True
        return False

    async def export_data(self, user_id, profile):
        return await export_cases(self.db, user_id, profile)

    async def delete_cases(self, user_id):
        return await delete_cases(self.db, user_id)
