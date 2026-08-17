"""SQLAlchemy model for the user ↔ topic mapping."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Own metadata — create_all() here never touches the host bot's tables."""


class SupportThread(Base):
    """One row per (bot, user): which forum topic carries their conversation."""

    __tablename__ = "support_threads"
    __table_args__ = (
        UniqueConstraint("bot_id", "user_id", name="uq_support_bot_user"),
        UniqueConstraint("bot_id", "thread_id", name="uq_support_bot_thread"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # One group can serve several bots, so the key is the pair, not the user
    # alone: the same person writing to two bots gets two topics.
    bot_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    thread_id: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
