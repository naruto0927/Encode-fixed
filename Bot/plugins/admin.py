import os
import asyncio
from datetime import datetime, timezone

from pyrogram import filters

from Bot import bot, OWNER_ID, TRIGGERS, LOG
from Bot.plugins.database.mongo_db import (
    get_all_users,
    get_user_count,
    ban_user,
    unban_user,
    is_banned,
    get_all_bans,
    set_bot_state,
    get_bot_state,
    get_all_history,
    get_pending_queue,
)
from Bot.utils.ffmpeg import humanbytes
from Bot.utils.telegram_helpers import respond, reply, edit, get_reply_message, safe_call

OWNER_FILTER = filters.user(OWNER_ID)


# ─── /users Command (Owner Only) ───

@bot.on_message(filters.command("users", prefixes=TRIGGERS) & OWNER_FILTER)
async def users_command(client, message):
    """List all authorized users."""
    all_users = await get_all_users()
    count = len(all_users)

    if count == 0:
        await respond(message, "**No authorized users.**")
        return

    text = f"**👥 Authorized Users ({count})**\n\n"

    for i, user_doc in enumerate(all_users, 1):
        uid = user_doc.get("user_id", "?")
        res = user_doc.get("resolution", "?")
        vcodec = user_doc.get("vcodec", "?")
        try:
            user = await bot.get_users(int(uid))
            name = getattr(user, "first_name", str(uid)) or str(uid)
        except Exception:
            name = str(uid)
        text += f"`{i}.` [{name}](tg://user?id={uid}) — `{res}` / `{vcodec}`\n"

        if len(text) > 3800:
            text += f"\n_...and {count - i} more_"
            break

    await respond(message, text, disable_web_page_preview=True)


# ─── /broadcast Command (Owner Only) ───

@bot.on_message(filters.command("broadcast", prefixes=TRIGGERS) & OWNER_FILTER)
async def broadcast_command(client, message):
    """Broadcast a message to all authorized users.

    Usage: /broadcast <message>
    Or reply to a message with /broadcast
    """
    reply_msg = await get_reply_message(message)
    text_parts = (message.text or "").split(None, 1)
    broadcast_text = None

    if reply_msg:
        pass  # Will forward
    elif len(text_parts) > 1:
        broadcast_text = text_parts[1]
    else:
        await respond(message, "**Usage:** `/broadcast <message>` or reply to a message with `/broadcast`")
        return

    all_users = await get_all_users()
    success = 0
    failed = 0
    status_msg = await respond(message, f"**Broadcasting to {len(all_users)} users...**")

    for user_doc in all_users:
        uid = user_doc.get("user_id")
        if uid == OWNER_ID:
            continue
        try:
            if reply_msg:
                await bot.forward_messages(uid, reply_msg.chat.id, reply_msg.id)
            else:
                await bot.send_message(uid, broadcast_text)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)

    await edit(
        status_msg,
        f"**Broadcast Complete**\n\n"
        f"**Success:** `{success}`\n"
        f"**Failed:** `{failed}`"
    )


# ─── /log Command (Owner Only) ───

@bot.on_message(filters.command("log", prefixes=TRIGGERS) & OWNER_FILTER)
async def log_command(client, message):
    """Send the error.log file to the owner."""
    log_path = "error.log"

    if not os.path.exists(log_path):
        await respond(message, "**No log file found.**")
        return

    file_size = os.path.getsize(log_path)
    if file_size == 0:
        await respond(message, "**Log file is empty.**")
        return

    try:
        await safe_call(
            lambda: message.reply_document(log_path, caption="**📄 Bot Log File:**", quote=False),
            what="send log file",
        )
    except Exception as e:
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
            tail = "".join(lines[-50:])
            await respond(message, f"**Last 50 log lines:**\n\n```\n{tail[:4000]}\n```")
        except Exception as e2:
            await respond(message, f"**Failed to send log:** `{e2}`")


# ═══════════════════════════════════════════
# /ban & /unban — Ban system (Owner Only)
# ═══════════════════════════════════════════

@bot.on_message(filters.command("ban", prefixes=TRIGGERS) & OWNER_FILTER)
async def ban_command(client, message):
    """Ban a user from using the bot.

    Usage: /ban <user_id> [reason]
    """
    parts = (message.text or "").split(None, 2)
    if len(parts) < 2:
        await respond(message, "**Usage:** `/ban <user_id> [reason]`")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await respond(message, "**Invalid user ID.**")
        return

    if target_id == OWNER_ID:
        await respond(message, "**Cannot ban the owner.**")
        return

    reason = parts[2] if len(parts) > 2 else "No reason specified"
    await ban_user(target_id, reason)

    try:
        user = await bot.get_users(target_id)
        name = getattr(user, "first_name", str(target_id))
    except Exception:
        name = str(target_id)

    await respond(message, f"**🚫 Banned** [{name}](tg://user?id={target_id})\n**Reason:** `{reason}`")
    LOG.info(f"Banned user {target_id}: {reason}")


@bot.on_message(filters.command("unban", prefixes=TRIGGERS) & OWNER_FILTER)
async def unban_command(client, message):
    """Unban a user.

    Usage: /unban <user_id>
    """
    parts = (message.text or "").split()
    if len(parts) < 2:
        await respond(message, "**Usage:** `/unban <user_id>`")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await respond(message, "**Invalid user ID.**")
        return

    result = await unban_user(target_id)
    if result:
        await respond(message, f"**✅ Unbanned** `{target_id}`")
    else:
        await respond(message, f"**User `{target_id}` was not banned.**")


@bot.on_message(filters.command("bans", prefixes=TRIGGERS) & OWNER_FILTER)
async def bans_command(client, message):
    """List all banned users."""
    bans = await get_all_bans()
    if not bans:
        await respond(message, "**No banned users.**")
        return

    text = f"**🚫 Banned Users ({len(bans)})**\n\n"
    for b in bans:
        uid = b.get("user_id", "?")
        reason = b.get("reason", "?")
        ts = b.get("banned_at", "?")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d")
        text += f"• `{uid}` — {reason} ({ts})\n"

        if len(text) > 3800:
            text += f"\n_...and more_"
            break

    await respond(message, text)


# ═══════════════════════════════════════════
# /maintenance — Maintenance mode (Owner Only)
# ═══════════════════════════════════════════

@bot.on_message(filters.command("maintenance", prefixes=TRIGGERS) & OWNER_FILTER)
async def maintenance_command(client, message):
    """Toggle maintenance mode.

    Usage:
      /maintenance on [message] — Enable maintenance
      /maintenance off — Disable maintenance
    """
    parts = (message.text or "").split(None, 2)
    if len(parts) < 2:
        current = await get_bot_state("maintenance")
        status = "enabled" if current else "disabled"
        msg = ""
        if current and isinstance(current, dict):
            msg = current.get("message", "")
        await respond(
            message,
            f"**🔧 Maintenance Mode:** `{status}`\n"
            f"**Message:** `{msg or 'default'}`\n\n"
            "`/maintenance on [message]` — Enable\n"
            "`/maintenance off` — Disable"
        )
        return

    action = parts[1].lower()
    if action == "on":
        maint_msg = parts[2] if len(parts) > 2 else "Bot is under maintenance. Please try again later."
        await set_bot_state("maintenance", {"enabled": True, "message": maint_msg})
        await respond(message, f"**🔧 Maintenance mode ENABLED.**\n**Message:** `{maint_msg}`")
        LOG.info("Maintenance mode enabled")
    elif action == "off":
        await set_bot_state("maintenance", None)
        await respond(message, "**✅ Maintenance mode DISABLED.**")
        LOG.info("Maintenance mode disabled")
    else:
        await respond(message, "**Usage:** `/maintenance on [message]` or `/maintenance off`")


# ═══════════════════════════════════════════
# /stats — Enhanced statistics (Owner Only)
# ═══════════════════════════════════════════

@bot.on_message(filters.command("stats", prefixes=TRIGGERS) & OWNER_FILTER)
async def stats_command(client, message):
    """Show comprehensive bot statistics."""
    user_count = await get_user_count()
    log_size = os.path.getsize("error.log") if os.path.exists("error.log") else 0

    dl_dir = "downloads"
    dl_count = len(os.listdir(dl_dir)) if os.path.exists(dl_dir) else 0

    from Bot.plugins.encoder import _task_queue, _active_tasks, MAX_CONCURRENT

    # Ban count
    bans = await get_all_bans()
    ban_count = len(bans) if bans else 0

    # Pending queue in DB
    pending_queue = await get_pending_queue()
    persist_count = len(pending_queue) if pending_queue else 0

    # Encoding history stats
    all_history = await get_all_history(limit=1000)
    total_encodes = len(all_history) if all_history else 0
    total_saved = 0
    for rec in (all_history or []):
        orig = rec.get("original_size", 0)
        enc = rec.get("encoded_size", 0)
        if orig > enc:
            total_saved += orig - enc

    # Maintenance status
    maint = await get_bot_state("maintenance")
    maint_status = "ON" if maint else "OFF"

    text = (
        "**📊 Bot Statistics**\n\n"
        f"**Authorized Users:** `{user_count}`\n"
        f"**Banned Users:** `{ban_count}`\n"
        f"**Maintenance Mode:** `{maint_status}`\n\n"
        f"**Queue Size:** `{len(_task_queue)}`\n"
        f"**Active Encodes:** `{_active_tasks}/{MAX_CONCURRENT}`\n"
        f"**Persistent Queue:** `{persist_count}`\n"
        f"**Files in Downloads:** `{dl_count}`\n\n"
        f"**Total Encodes (history):** `{total_encodes}`\n"
        f"**Total Space Saved:** `{humanbytes(total_saved)}`\n"
        f"**Log File Size:** `{humanbytes(log_size)}`"
    )
    await respond(message, text)
