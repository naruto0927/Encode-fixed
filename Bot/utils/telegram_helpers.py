"""
Small compatibility/utility layer used across all plugins to keep the
Pyrogram migration mechanical and low-risk:

- `Button` / `markup()` let existing code that builds Telethon-style
  `Button.inline(...)` / `Button.url(...)` layouts keep doing so almost
  unchanged -- only the import changes, plus wrapping the outer list with
  `markup()` when passing it as `reply_markup=`.
- `safe_call()` centralizes FloodWait handling with a bounded number of
  retries, so a flood-wait can never turn into an infinite retry loop.
- `get_reply_message()` mirrors Telethon's `event.get_reply_message()`.
- `make_progress_callback()` produces a real `async def` closure (not a
  lambda/partial) because Pyrogram only awaits progress callbacks it can
  positively identify as coroutine functions via `inspect.iscoroutinefunction`
  -- a lambda that calls an async function returns an un-awaited coroutine,
  which silently breaks progress reporting instead of raising an error.
"""

import asyncio

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError

from Bot import LOG

MAX_FLOODWAIT_RETRIES = 3
MAX_FLOODWAIT_SLEEP = 300  # seconds -- never wait longer than this in one go


class Button:
    """Drop-in-ish replacement for `telethon.Button` used when building
    keyboard layouts. Produces Pyrogram `InlineKeyboardButton`s.
    """

    @staticmethod
    def inline(text, data):
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return InlineKeyboardButton(text, callback_data=data)

    @staticmethod
    def url(text, url):
        return InlineKeyboardButton(text, url=url)


def markup(rows):
    """Wrap a list-of-rows of InlineKeyboardButton into an InlineKeyboardMarkup.
    Returns None for an empty/falsy input so `reply_markup=markup(x)` is always
    safe to pass even when `x` is `None` or `[]`.
    """
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def safe_call(coro_factory, *, what="Telegram call", max_retries=MAX_FLOODWAIT_RETRIES):
    """Run an async Pyrogram operation, retrying on FloodWait a bounded number
    of times. Never retries indefinitely: once max_retries is exceeded, or a
    single FloodWait is longer than MAX_FLOODWAIT_SLEEP, the exception is
    re-raised so the caller's own error handling takes over.

    `coro_factory` must be a zero-argument callable that returns a *fresh*
    coroutine on each call (e.g. `lambda: message.edit_text(x)`), since a
    coroutine object can only be awaited once.
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except FloodWait as e:
            attempt += 1
            wait = getattr(e, "value", None) or getattr(e, "x", 5)
            if attempt > max_retries or wait > MAX_FLOODWAIT_SLEEP:
                LOG.warning(f"{what}: FloodWait {wait}s exceeded retry budget ({attempt - 1}/{max_retries}); giving up.")
                raise
            LOG.warning(f"{what}: FloodWait {wait}s, attempt {attempt}/{max_retries} -- sleeping.")
            await asyncio.sleep(wait)
        except RPCError:
            # Not a flood-wait -- don't swallow it, let the caller decide.
            raise


async def respond(message, text, **kwargs):
    """Telethon `.respond()`-equivalent: send a new message into the chat
    WITHOUT quoting the triggering message (matches Telethon's default)."""
    kwargs.setdefault("quote", False)
    return await safe_call(lambda: message.reply_text(text, **kwargs), what="respond")


async def reply(message, text, **kwargs):
    """Telethon `.reply()`-equivalent: reply, quoting the triggering message."""
    kwargs.setdefault("quote", True)
    return await safe_call(lambda: message.reply_text(text, **kwargs), what="reply")


async def edit(message, text, **kwargs):
    """Telethon `.edit()`-equivalent for a message the bot itself sent."""
    return await safe_call(lambda: message.edit_text(text, **kwargs), what="edit")


async def get_reply_message(message):
    """Mirrors Telethon's `event.get_reply_message()`: return the full Message
    being replied to, fetching it explicitly if it wasn't already embedded.
    """
    embedded = getattr(message, "reply_to_message", None)
    if embedded:
        return embedded
    reply_id = getattr(message, "reply_to_message_id", None)
    if not reply_id:
        return None
    try:
        return await message._client.get_messages(message.chat.id, reply_id)
    except Exception as e:
        LOG.warning(f"get_reply_message: failed to fetch reply {reply_id}: {e}")
        return None


def make_progress_callback(progress_fn, message, status_msg, start_time, label):
    """Build a real `async def` closure of signature (current, total) that
    forwards to `progress_fn(current, total, message, status_msg, start_time,
    label)`. MUST be a genuine async def (not a lambda/functools.partial) --
    see module docstring for why.
    """
    async def _cb(current, total):
        try:
            await progress_fn(current, total, message, status_msg, start_time, label)
        except Exception as e:
            LOG.warning(f"Progress callback error: {e}")
    return _cb


def sender_name(user) -> str:
    """Best-effort display name from a Pyrogram User, mirroring the old
    `getattr(sender, 'first_name', 'User')` pattern used throughout."""
    if user is None:
        return "User"
    return getattr(user, "first_name", None) or "User"
