from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    hide_parameters=True,
    **({"poolclass": NullPool} if settings.DB_NULL_POOL else {}),
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
