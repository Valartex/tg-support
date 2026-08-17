"""Support router: private chat ⇄ forum topics in the support supergroup.

User side  — messages sent while the support session is open are copied into
the user's topic, which is created on first contact.
Group side — anything an operator writes inside a topic is copied back to the
matching user. Topics belonging to another bot are silently ignored, so one
group can serve every bot you run.
"""
from __future__ import annotations

import asyncio
import html
import logging
from collections import defaultdict

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from tg_support.config import SupportConfig
from tg_support.storage import SupportStorage
from tg_support.antiflood import RateLimiter

log = logging.getLogger("tg_support")

TOPIC_NAME_LIMIT = 128
EXIT_CALLBACK = "tgsup:exit"

# Content types worth copying in either direction. Everything else — polls,
# dice, and the forum service messages Telegram posts into topics — is skipped.
RELAYABLE = {
    ContentType.TEXT,
    ContentType.PHOTO,
    ContentType.DOCUMENT,
    ContentType.VIDEO,
    ContentType.VIDEO_NOTE,
    ContentType.VOICE,
    ContentType.AUDIO,
    ContentType.ANIMATION,
    ContentType.STICKER,
    ContentType.LOCATION,
    ContentType.CONTACT,
}


class Support(StatesGroup):
    chatting = State()


class SupportService:
    """Topic bookkeeping. Kept separate from the handlers so the host bot can
    reuse it — e.g. to push a payment notice into a user's topic."""

    def __init__(self, config: SupportConfig) -> None:
        self.config = config
        self.storage = SupportStorage(config.engine, config.database_url)
        self.limiter = RateLimiter(config.rate_limit_count, config.rate_limit_seconds)
        # Two quick messages from the same user must not create two topics.
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def init(self) -> None:
        await self.storage.init()

    async def get_thread_id(self, bot: Bot, user: User) -> int:
        """Return the user's topic id, opening the topic on first contact."""
        async with self._locks[user.id]:
            thread_id = await self.storage.get_thread_id(bot.id, user.id)
            if thread_id is not None:
                return thread_id
            return await self._open_topic(bot, user)

    async def _open_topic(self, bot: Bot, user: User) -> int:
        topic = await bot.create_forum_topic(
            chat_id=self.config.support_chat_id, name=self._topic_name(user)
        )
        await self.storage.save(bot.id, user.id, topic.message_thread_id)
        await bot.send_message(
            chat_id=self.config.support_chat_id,
            message_thread_id=topic.message_thread_id,
            text=await self._header(user),
            parse_mode="HTML",
        )
        log.info("support topic %s opened for user %s", topic.message_thread_id, user.id)
        return topic.message_thread_id

    def _topic_name(self, user: User) -> str:
        parts = [self.config.bot_label, user.full_name or str(user.id)]
        return " · ".join(p for p in parts if p)[:TOPIC_NAME_LIMIT]

    async def _header(self, user: User) -> str:
        extra = ""
        if self.config.user_info:
            try:
                extra = await self.config.user_info(user.id)
            except Exception:  # noqa: BLE001 - a broken hook must not block support
                log.exception("user_info hook failed for %s", user.id)
        return self.config.texts.topic_header.format(
            label=html.escape(self.config.bot_label),
            name=html.escape(user.full_name or "—"),
            user_id=user.id,
            username=f"@{user.username}" if user.username else "—",
            extra=extra,
        )

    async def relay_to_group(self, bot: Bot, message: Message) -> None:
        """Copy a user's message into their topic, healing a stale mapping."""
        thread_id = await self.get_thread_id(bot, message.from_user)
        try:
            await self._copy_to_topic(bot, message, thread_id)
        except TelegramBadRequest as e:
            reason = str(e).lower()
            if "closed" in reason:
                # Operator closed the topic; a new question reopens it.
                await bot.reopen_forum_topic(self.config.support_chat_id, thread_id)
                await self._copy_to_topic(bot, message, thread_id)
            elif "thread not found" in reason or "topic_deleted" in reason:
                # Topic was deleted by hand — forget it and start a fresh one.
                await self.storage.forget_thread(bot.id, thread_id)
                thread_id = await self.get_thread_id(bot, message.from_user)
                await self._copy_to_topic(bot, message, thread_id)
            else:
                raise

    async def _copy_to_topic(self, bot: Bot, message: Message, thread_id: int) -> None:
        await bot.copy_message(
            chat_id=self.config.support_chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id,
        )


def create_support_router(config: SupportConfig, service: SupportService | None = None) -> Router:
    """Build the router. Include it *before* the host bot's own routers so an
    open support session wins over the normal message flow."""
    service = service or SupportService(config)
    texts = config.texts
    router = Router(name="tg_support")

    # Menu labels and commands must reach the host bot instead of the operator.
    escape_texts = set(config.passthrough_texts)
    if config.entry_button:
        escape_texts.discard(config.entry_button)

    def exit_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=texts.exit_button, callback_data=EXIT_CALLBACK)]
            ]
        )

    # ------------------------------------------------------------------ group

    @router.message(
        F.chat.id == config.support_chat_id,
        F.message_thread_id,
        F.content_type.in_(RELAYABLE),
        ~F.from_user.is_bot,
    )
    async def relay_to_user(message: Message, bot: Bot, fsm_storage: BaseStorage) -> None:
        user_id = await service.storage.get_user_id(bot.id, message.message_thread_id)
        if user_id is None:
            return  # another bot's topic, or a topic opened by hand

        if message.text and message.text.startswith("/"):
            await _operator_command(message, bot, fsm_storage, user_id)
            return

        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except TelegramForbiddenError:
            await message.reply(texts.user_blocked)
            return

        # Keep the conversation going: the user's next message goes to support
        # without them having to press the button again.
        await _set_user_state(fsm_storage, bot, user_id, Support.chatting)

    async def _operator_command(
        message: Message, bot: Bot, fsm_storage: BaseStorage, user_id: int
    ) -> None:
        """Handle /close inside a topic. Commands are never sent to the user."""
        command = message.text.split(maxsplit=1)[0].lstrip("/").split("@")[0].lower()
        if command != "close":
            return
        await _set_user_state(fsm_storage, bot, user_id, None)
        await message.answer(texts.topic_resolved)
        try:
            await bot.close_forum_topic(config.support_chat_id, message.message_thread_id)
        except TelegramBadRequest as e:
            log.warning("closing topic %s failed: %s", message.message_thread_id, e)

    async def _set_user_state(
        fsm_storage: BaseStorage, bot: Bot, user_id: int, state: State | None
    ) -> None:
        """Reach into the user's private-chat FSM from the group handler."""
        key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
        await FSMContext(storage=fsm_storage, key=key).set_state(state)

    @router.message(F.chat.id == config.support_chat_id)
    async def swallow_support_chat(message: Message) -> None:
        """Stop here: nothing in the support group is meant for the host bot.

        Without this, chatter in the group's General section reaches handlers
        written for private chats — a pasted link read as user input, and so on.
        """

    # ------------------------------------------------------------------- user

    @router.message(Command(config.entry_command))
    async def open_support(message: Message, state: FSMContext) -> None:
        await state.set_state(Support.chatting)
        await message.answer(texts.opened, reply_markup=exit_keyboard())

    if config.entry_button:
        router.message.register(
            open_support, F.chat.type == "private", F.text == config.entry_button
        )

    @router.callback_query(F.data == EXIT_CALLBACK)
    async def close_support(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(texts.closed)

    @router.message(Support.chatting, F.chat.type == "private")
    async def relay_from_user(message: Message, state: FSMContext, bot: Bot) -> None:
        text = message.text or ""

        # Let commands and the host bot's menu buttons out of the session.
        if text.startswith("/") or text in escape_texts:
            await state.clear()
            raise SkipHandler

        if message.content_type not in RELAYABLE:
            await message.answer(texts.failed)
            return

        if not service.limiter.allow(message.from_user.id):
            await message.answer(texts.rate_limited)
            return

        try:
            await service.relay_to_group(bot, message)
        except (TelegramBadRequest, TelegramForbiddenError):
            log.exception("relaying message from %s failed", message.from_user.id)
            await message.answer(texts.failed)
            return

        if config.confirm_each_message:
            await message.answer(texts.sent)

    return router
