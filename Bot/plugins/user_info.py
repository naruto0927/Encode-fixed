from pyrogram import filters

from Bot import bot, OWNER_ID, TRIGGERS, LOG
from Bot.utils.user_info import get_users, user_check_template
from Bot.utils.telegram_helpers import Button, markup, reply, respond, safe_call, get_reply_message


@bot.on_message(filters.command("info", prefixes=TRIGGERS))
async def info_check(client, message):
    target_id = None

    # Check if replying to someone
    reply_msg = await get_reply_message(message)
    if reply_msg and reply_msg.from_user:
        target_id = reply_msg.from_user.id

    # Check if argument provided
    if target_id is None:
        args = (message.text or "").split(None, 1)
        if len(args) > 1:
            arg = args[1].strip().lstrip("@")
            if arg.isdigit():
                target_id = int(arg)
            else:
                # Try to resolve username
                try:
                    user = await bot.get_users(arg)
                    target_id = user.id
                except Exception:
                    await reply(message, "**User not found.**")
                    return

    if target_id is None:
        await reply(message, "**Usage:** `/info <user_id or @username>` or reply to a message.")
        return

    try:
        user_info = await get_users(target_id)
        if user_info is None:
            await reply(message, "**User not found.**")
            return

        text = await user_check_template(user_info[0], user_info[1], user_info[2], user_info[3], user_info[4], user_info[6])

        buttons = [
            [
                Button.inline("ᴀᴜᴛʜᴏʀɪᴢᴇ", f"users_auth-{user_info[6]}".encode()),
                Button.inline("ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇ", f"users_unauth-{user_info[6]}".encode()),
            ],
            [Button.inline("ʀᴇǫᴜᴇsᴛ", f"users_request-{user_info[6]}".encode())],
        ]

        caption = "`-------`**ᴜsᴇʀ**`-------`\n\n" + text

        if user_info[5]:
            # Send by file_id directly -- no download/re-upload round-trip needed.
            await safe_call(
                lambda: message.reply_photo(user_info[5].file_id, caption=caption, reply_markup=markup(buttons)),
                what="info command photo",
            )
        else:
            await respond(message, caption, reply_markup=markup(buttons))

    except Exception as e:
        LOG.warning(f"Error fetching user info: {e}")
        await reply(message, f"**Error:** `{e}`")
