"""Persistence for the user ↔ topic mapping."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tg_support.models import Base, SupportThread


class SupportStorage:
    """Thin repository over `support_threads`.

    Takes the host bot's engine when given one, so the mapping lands in the
    same database file and there is nothing extra to back up.
    """

    def __init__(
        self,
        engine: AsyncEngine | None = None,
        database_url: str | None = None,
    ) -> None:
        if engine is None:
            if not database_url:
                raise ValueError("SupportStorage needs either engine or database_url")
            engine = create_async_engine(database_url, echo=False)
        self._engine = engine
        self._session = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

    async def init(self) -> None:
        """Create the mapping table if it doesn't exist yet."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_thread_id(self, bot_id: int, user_id: int) -> int | None:
        async with self._session() as session:
            return await session.scalar(
                select(SupportThread.thread_id).where(
                    SupportThread.bot_id == bot_id,
                    SupportThread.user_id == user_id,
                )
            )

    async def get_user_id(self, bot_id: int, thread_id: int) -> int | None:
        async with self._session() as session:
            return await session.scalar(
                select(SupportThread.user_id).where(
                    SupportThread.bot_id == bot_id,
                    SupportThread.thread_id == thread_id,
                )
            )

    async def save(self, bot_id: int, user_id: int, thread_id: int) -> None:
        async with self._session() as session:
            session.add(
                SupportThread(bot_id=bot_id, user_id=user_id, thread_id=thread_id)
            )
            await session.commit()

    async def forget_thread(self, bot_id: int, thread_id: int) -> None:
        """Drop the mapping after the operator deleted the topic."""
        async with self._session() as session:
            await session.execute(
                delete(SupportThread).where(
                    SupportThread.bot_id == bot_id,
                    SupportThread.thread_id == thread_id,
                )
            )
            await session.commit()
