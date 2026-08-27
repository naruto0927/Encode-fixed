import os
import sys

from pyrogram import filters

from Bot import bot, OWNER_ID, TRIGGERS
from Bot.utils.telegram_helpers import Button, markup, reply


@bot.on_message(filters.command("restart", prefixes=TRIGGERS) & filters.user(OWNER_ID))
async def restart_bot(client, message):
    await reply(
        message,
        "**Restarting...**",
        reply_markup=markup([[Button.url("Dev", "https://t.me/sohailkhan_indianime")]]),
    )
    os.execl(sys.executable, sys.executable, "-m", "Bot")
