import io
import sys
import os
import traceback
import asyncio

from pyrogram import filters

from Bot import bot, OWNER_ID, TRIGGERS, LOG
from Bot.utils.telegram_helpers import respond, reply, safe_call


# ─── /eval - Execute Python code ───

@bot.on_message(filters.command("eval", prefixes=TRIGGERS) & filters.user(OWNER_ID))
async def eval_handler(client, message):
    text = message.text or ""
    parts = text.split(None, 1)
    if len(parts) < 2:
        await reply(message, "**Usage:** `/eval <code>`")
        return
    cmd = parts[1]
    status_msg = await reply(message, "**Processing...**")

    reply_to = message.reply_to_message_id or message.id

    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()

    stdout, stderr, exc = None, None, None
    try:
        await _aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = exc or stderr or stdout or "Success"

    final_output = f"**EVAL:** `{cmd}`\n\n**OUTPUT:**\n`{evaluation.strip()}`"

    if len(final_output) > 4096:
        with io.BytesIO(final_output.encode()) as out_file:
            out_file.name = "eval.txt"
            await safe_call(
                lambda: bot.send_document(
                    message.chat.id, out_file, caption=f"`{cmd[:100]}`", reply_to_message_id=reply_to,
                ),
                what="send eval output file",
            )
    else:
        await safe_call(
            lambda: bot.send_message(message.chat.id, final_output, reply_to_message_id=reply_to),
            what="send eval output",
        )

    try:
        await status_msg.delete()
    except Exception:
        pass


async def _aexec(code, client, message):
    exec(
        "async def __aexec(client, message): "
        + "".join(f"\n {line}" for line in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)


# ─── /term - Execute shell commands ───

@bot.on_message(filters.command("term", prefixes=TRIGGERS) & filters.user(OWNER_ID))
async def terminal_handler(client, message):
    text = message.text or ""
    cmd_text = text.split(None, 1)
    if len(cmd_text) < 2:
        await reply(message, "**Usage:** `/term echo hello`")
        return

    command = cmd_text[1]

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()

        result = ""
        if output:
            result += f"**stdout:**\n```\n{output}\n```\n"
        if error:
            result += f"**stderr:**\n```\n{error}\n```\n"
        if not result:
            result = "**No output.**"

    except asyncio.TimeoutError:
        result = "**Error:** Command timed out (120s)."
    except Exception:
        result = f"**Error:**\n```\n{traceback.format_exc()}\n```"

    if len(result) > 4096:
        filename = "output.txt"
        with open(filename, "w") as f:
            f.write(result)
        await safe_call(
            lambda: bot.send_document(message.chat.id, filename, reply_to_message_id=message.id, caption="`Output`"),
            what="send term output file",
        )
        os.remove(filename)
    else:
        await respond(message, result)
