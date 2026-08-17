"""Configuration for the support module."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine

from tg_support.texts import SupportTexts

# Extra context for the topic header: receives the Telegram user id, returns a
# ready HTML snippet (plan, payment status — whatever the host bot knows).
UserInfoHook = Callable[[int], Awaitable[str]]


@dataclass(slots=True)
class SupportConfig:
    # Forum supergroup holding the topics. Negative, starts with -100.
    support_chat_id: int

    # Where the mapping table lives. Pass the host bot's engine to keep one
    # database file, or a URL to get a separate one.
    engine: AsyncEngine | None = None
    database_url: str | None = None

    # Prefix in the topic title, so one group can serve several bots.
    bot_label: str = ""

    # How the user enters support mode.
    entry_command: str = "support"
    entry_button: str | None = "🆘 Поддержка"

    # Texts that must escape the support session instead of being relayed —
    # the host bot's reply-keyboard labels. Anything starting with "/" always
    # escapes, so commands need not be listed.
    passthrough_texts: set[str] = field(default_factory=set)

    # At most `rate_limit_count` messages per `rate_limit_seconds`, per user.
    rate_limit_count: int = 10
    rate_limit_seconds: int = 60

    # Confirm every relayed message. Off by default: the operator's reply is
    # confirmation enough, and a receipt after each line gets noisy.
    confirm_each_message: bool = False

    user_info: UserInfoHook | None = None
    texts: SupportTexts = field(default_factory=SupportTexts)

    def __post_init__(self) -> None:
        if self.engine is None and not self.database_url:
            raise ValueError("SupportConfig needs either engine= or database_url=")
