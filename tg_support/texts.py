"""User- and operator-facing strings. Override via SupportConfig(texts=...)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SupportTexts:
    """Every string the module can send. All defaults are Russian."""

    # --- shown to the user, in the private chat ---
    opened: str = (
        "✍️ Опишите вопрос одним сообщением — можно приложить скриншот.\n"
        "Ответ придёт сюда же."
    )
    sent: str = "✅ Отправлено. Ответим здесь."
    closed: str = "Вы вышли из режима поддержки."
    exit_button: str = "⬅️ Выйти из поддержки"
    rate_limited: str = "Слишком много сообщений подряд — подождите минуту, пожалуйста."
    failed: str = "Не удалось отправить сообщение. Попробуйте ещё раз чуть позже."

    # --- shown in the support group ---
    # Placeholders: {label} {name} {user_id} {username} {extra}
    topic_header: str = (
        "👤 <b>{name}</b>\n"
        "ID: <code>{user_id}</code>\n"
        "Username: {username}\n"
        "{extra}\n"
        "<i>Пишите в этой теме — сообщение уйдёт пользователю. /close — закрыть обращение.</i>"
    )
    user_blocked: str = "⚠️ Пользователь заблокировал бота — ответ не доставлен."
    topic_resolved: str = "✅ Обращение закрыто."
