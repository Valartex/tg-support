"""Support channel for aiogram bots, built on Telegram forum topics."""
from __future__ import annotations

from tg_support.config import SupportConfig, UserInfoHook
from tg_support.router import Support, SupportService, create_support_router
from tg_support.storage import SupportStorage
from tg_support.texts import SupportTexts

__all__ = [
    "Support",
    "SupportConfig",
    "SupportService",
    "SupportStorage",
    "SupportTexts",
    "UserInfoHook",
    "create_support_router",
]

__version__ = "0.1.0"
