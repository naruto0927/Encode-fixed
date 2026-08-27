import os
import re
import asyncio

from pyrogram import filters

from Bot import bot, OWNER_ID, TRIGGERS, LOG
from Bot.plugins.database.mongo_db import (
    check_user_mdb,
    get_user_field,
    update_user_field,
    save_profile,
    load_profile,
    delete_profile,
    list_profiles,
    get_history,
)
from Bot.utils.decorators import _get_stream_info, check_hwaccel_available
from Bot.utils.ffmpeg import generate_sample, humanbytes, get_video_duration
from Bot.utils.telegram_helpers import respond, reply, edit, get_reply_message, safe_call


# ═══════════════════════════════════════════
# /rename — Custom rename pattern
# ═══════════════════════════════════════════

@bot.on_message(filters.command("rename", prefixes=TRIGGERS))
async def rename_command(client, message):
    """Set a custom rename pattern for encoded files.

    Usage: /rename [Erika] {title} [{res}].{ext}
    Placeholders: {title}, {res}, {codec}, {ext}
    Use /rename off to disable.
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        current = await get_user_field(user_id, "rename_pattern", "")
        text = "**Custom Rename Pattern**\n\n"
        text += f"**Current:** `{current or 'disabled'}`\n\n"
        text += "**Usage:** `/rename [Erika] {title} [{res}].{ext}`\n"
        text += "**Placeholders:** `{title}`, `{res}`, `{codec}`, `{ext}`\n"
        text += "**Disable:** `/rename off`"
        await respond(message, text)
        return

    pattern = parts[1].strip()
    if pattern.lower() == "off":
        await update_user_field(user_id, "rename_pattern", "")
        await respond(message, "**Rename pattern disabled.** Using original filenames.")
    else:
        await update_user_field(user_id, "rename_pattern", pattern)
        await respond(message, f"**Rename pattern set:** `{pattern}`")


# ═══════════════════════════════════════════
# /profile — Preset profiles
# ═══════════════════════════════════════════

@bot.on_message(filters.command("profile", prefixes=TRIGGERS))
async def profile_command(client, message):
    """Manage encoding profiles.

    Usage:
      /profile save <n> — Save current settings as a profile
      /profile load <n> — Load a saved profile
      /profile delete <n> — Delete a profile
      /profile list — List all profiles
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await respond(
            message,
            "**Profile Manager**\n\n"
            "`/profile save <n>` — Save current settings\n"
            "`/profile load <n>` — Load a profile\n"
            "`/profile delete <n>` — Delete a profile\n"
            "`/profile list` — List all profiles"
        )
        return

    action = parts[1].lower()

    if action == "save" and len(parts) >= 3:
        name = parts[2]
        result = await save_profile(user_id, name)
        if result:
            await respond(message, f"**Profile `{name}` saved!**")
        else:
            await respond(message, "**Failed to save profile.** Are you authorized?")

    elif action == "load" and len(parts) >= 3:
        name = parts[2]
        result = await load_profile(user_id, name)
        if result:
            text = f"**Profile `{name}` loaded!**\n\n"
            for k, v in result.items():
                text += f"**{k}:** `{v}`\n"
            await respond(message, text)
        else:
            await respond(message, f"**Profile `{name}` not found.**")

    elif action == "delete" and len(parts) >= 3:
        name = parts[2]
        result = await delete_profile(user_id, name)
        if result:
            await respond(message, f"**Profile `{name}` deleted.**")
        else:
            await respond(message, f"**Profile `{name}` not found.**")

    elif action == "list":
        profiles = await list_profiles(user_id)
        if not profiles:
            await respond(message, "**No saved profiles.**")
            return
        text = "**Your Profiles:**\n\n"
        for p in profiles:
            text += f"• `{p['name']}` — {p.get('resolution', '?')} / {p.get('vcodec', '?')} / CRF {p.get('crf', '?')}\n"
        await respond(message, text)

    else:
        await respond(message, "**Invalid usage.** Try `/profile` for help.")


# ═══════════════════════════════════════════
# /trim — Trim video before encoding
# ═══════════════════════════════════════════

@bot.on_message(filters.command("trim", prefixes=TRIGGERS))
async def trim_command(client, message):
    """Reply to a video with /trim <start> <end> to encode only a portion.

    Usage: /trim 00:05:00 00:45:00
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    reply_msg = await get_reply_message(message)
    if not reply_msg or not (reply_msg.video or reply_msg.document):
        await respond(message, "**Reply to a video** with `/trim <start> <end>`\n\nExample: `/trim 00:05:00 00:45:00`")
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await respond(message, "**Usage:** `/trim <start_time> <end_time>`\n\nExample: `/trim 00:05:00 00:45:00`")
        return

    trim_start = parts[1]
    trim_end = parts[2]

    # Validate time format (basic check)
    time_pattern = r"^\d{1,2}(:\d{2}){0,2}(\.\d+)?$"
    if not re.match(time_pattern, trim_start) or not re.match(time_pattern, trim_end):
        await respond(message, "**Invalid time format.** Use `HH:MM:SS` or `MM:SS` or seconds.")
        return

    await respond(message, f"**Trimming:** `{trim_start}` → `{trim_end}` and encoding...")

    # Use the encoder's _check_and_enqueue with trim params
    from Bot.plugins.encoder import _check_and_enqueue
    await _check_and_enqueue(reply_msg, trim_start=trim_start, trim_end=trim_end)


# ═══════════════════════════════════════════
# /sample — Generate a preview clip
# ═══════════════════════════════════════════

@bot.on_message(filters.command("sample", prefixes=TRIGGERS))
async def sample_command(client, message):
    """Reply to a video with /sample [duration] to get a preview clip.

    Usage: /sample 30  (default: 30 seconds)
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    reply_msg = await get_reply_message(message)
    if not reply_msg or not (reply_msg.video or reply_msg.document):
        await respond(message, "**Reply to a video** with `/sample [duration_seconds]`")
        return

    parts = (message.text or "").split()
    duration = 30
    if len(parts) >= 2:
        try:
            duration = int(parts[1])
            duration = max(5, min(duration, 120))
        except ValueError:
            pass

    status_msg = await respond(message, "**Generating sample clip...**")

    filepath = None
    try:
        # Download video
        filepath = await bot.download_media(reply_msg, file_name="downloads/")
        if not filepath:
            await edit(status_msg, "**Download failed.**")
            return

        # Get duration to calculate start point (start at 30s or 10% in)
        vid_duration = get_video_duration(filepath)
        start_at = "00:00:30"
        if vid_duration > 0:
            start_sec = max(0, int(vid_duration * 0.1))
            start_at = f"{start_sec // 3600:02d}:{(start_sec % 3600) // 60:02d}:{start_sec % 60:02d}"

        sample_path = await generate_sample(filepath, duration, start_at)

        if sample_path:
            await safe_call(
                lambda: bot.send_video(
                    message.chat.id,
                    sample_path,
                    caption=f"**Sample clip** ({duration}s)",
                    reply_to_message_id=reply_msg.id,
                ),
                what="send sample clip",
            )
            await status_msg.delete()
            os.remove(sample_path)
        else:
            await edit(status_msg, "**Failed to generate sample.**")

    except Exception as e:
        LOG.error(f"Sample generation error: {e}")
        try:
            await edit(status_msg, f"**Error:** `{e}`")
        except Exception:
            pass
    finally:
        # Clean up
        if filepath and os.path.exists(filepath):
            os.remove(filepath)


# ═══════════════════════════════════════════
# /tracks — Audio/subtitle track selection
# ═══════════════════════════════════════════

@bot.on_message(filters.command("tracks", prefixes=TRIGGERS))
async def tracks_command(client, message):
    """View/set audio and subtitle track preferences.

    Usage:
      /tracks — Show current settings
      /tracks audio 0,1 — Keep audio tracks 0 and 1
      /tracks sub 0 — Keep subtitle track 0
      /tracks audio all — Keep all audio tracks
      /tracks sub all — Keep all subtitle tracks
    Or reply to a video with /tracks to see available streams.
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    parts = (message.text or "").split()

    # If replying to a video, show stream info
    reply_msg = await get_reply_message(message)
    if reply_msg and (reply_msg.video or reply_msg.document) and len(parts) == 1:
        status_msg = await respond(message, "**Analyzing streams...**")
        filepath = None
        try:
            filepath = await bot.download_media(reply_msg, file_name="downloads/")
            if filepath:
                info = _get_stream_info(filepath)
                text = "**📋 Available Streams:**\n\n"

                if info["audio_streams"]:
                    text += "**Audio Tracks:**\n"
                    for a in info["audio_streams"]:
                        text += f"  `{a['index']}` — {a['codec']} / {a['lang']} / {a['title']}\n"
                else:
                    text += "**Audio:** None found\n"

                if info["subtitle_streams"]:
                    text += "\n**Subtitle Tracks:**\n"
                    for s in info["subtitle_streams"]:
                        text += f"  `{s['index']}` — {s['codec']} / {s['lang']} / {s['title']}\n"
                else:
                    text += "\n**Subtitles:** None found\n"

                text += "\n**Set tracks:** `/tracks audio 0,1` or `/tracks sub 0`"
                await edit(status_msg, text)
            else:
                await edit(status_msg, "**Failed to download for analysis.**")
        except Exception as e:
            await edit(status_msg, f"**Error:** `{e}`")
        finally:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        return

    if len(parts) == 1:
        # Show current settings
        audio_tracks = await get_user_field(user_id, "audio_tracks", "")
        sub_tracks = await get_user_field(user_id, "subtitle_tracks", "")
        text = (
            "**🎵 Track Settings**\n\n"
            f"**Audio tracks:** `{audio_tracks or 'all'}`\n"
            f"**Subtitle tracks:** `{sub_tracks or 'all'}`\n\n"
            "**Set:** `/tracks audio 0,1` or `/tracks sub 0`\n"
            "**Reset:** `/tracks audio all` or `/tracks sub all`\n"
            "**Analyze:** Reply to a video with `/tracks`"
        )
        await respond(message, text)
        return

    if len(parts) >= 3:
        track_type = parts[1].lower()
        value = parts[2].strip()

        if track_type in ("audio", "a"):
            if value.lower() == "all":
                await update_user_field(user_id, "audio_tracks", "")
                await respond(message, "**Audio tracks reset to all.**")
            else:
                await update_user_field(user_id, "audio_tracks", value)
                await respond(message, f"**Audio tracks set to:** `{value}`")

        elif track_type in ("sub", "subtitle", "s"):
            if value.lower() == "all":
                await update_user_field(user_id, "subtitle_tracks", "")
                await respond(message, "**Subtitle tracks reset to all.**")
            else:
                await update_user_field(user_id, "subtitle_tracks", value)
                await respond(message, f"**Subtitle tracks set to:** `{value}`")
        else:
            await respond(message, "**Invalid track type.** Use `audio` or `sub`.")
    else:
        await respond(message, "**Usage:** `/tracks audio 0,1` or `/tracks sub 0`")


# ═══════════════════════════════════════════
# /watermark — Set text/image watermark
# ═══════════════════════════════════════════

@bot.on_message(filters.command("watermark", prefixes=TRIGGERS))
async def watermark_command(client, message):
    """Set or remove watermark.

    Usage:
      /watermark <text> — Set text watermark
      /watermark off — Remove watermark
    Reply to an image with /watermark to set image watermark.
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    reply_msg = await get_reply_message(message)
    parts = (message.text or "").split(None, 1)

    # Reply to image = set image watermark
    if reply_msg and reply_msg.photo:
        status_msg = await respond(message, "**Saving watermark image...**")
        try:
            wm_dir = "watermarks_user"
            os.makedirs(wm_dir, exist_ok=True)
            wm_path = os.path.join(wm_dir, f"wm_{user_id}.png")
            await bot.download_media(reply_msg, file_name=wm_path)
            await update_user_field(user_id, "watermark_image", wm_path)
            await update_user_field(user_id, "watermark_text", "")
            await edit(status_msg, "**Image watermark saved!** It will overlay on your encoded videos.")
        except Exception as e:
            await edit(status_msg, f"**Error:** `{e}`")
        return

    if len(parts) < 2:
        current_text = await get_user_field(user_id, "watermark_text", "")
        current_img = await get_user_field(user_id, "watermark_image", "")
        status = "text" if current_text else ("image" if current_img else "none")
        text = (
            "**🔖 Watermark Settings**\n\n"
            f"**Type:** `{status}`\n"
            f"**Text:** `{current_text or 'none'}`\n"
            f"**Image:** `{'set' if current_img else 'none'}`\n\n"
            "**Commands:**\n"
            "`/watermark <text>` — Text watermark\n"
            "`/watermark off` — Remove all\n"
            "Reply to image with `/watermark` — Image watermark"
        )
        await respond(message, text)
        return

    wm_text = parts[1].strip()
    if wm_text.lower() == "off":
        await update_user_field(user_id, "watermark_text", "")
        await update_user_field(user_id, "watermark_image", "")
        await respond(message, "**Watermark removed.**")
    else:
        await update_user_field(user_id, "watermark_text", wm_text)
        await update_user_field(user_id, "watermark_image", "")
        await respond(message, f"**Text watermark set:** `{wm_text}`")


# ═══════════════════════════════════════════
# /schedule — Scheduled encoding
# ═══════════════════════════════════════════

@bot.on_message(filters.command("schedule", prefixes=TRIGGERS))
async def schedule_command(client, message):
    """Set encoding schedule.

    Usage:
      /schedule off-peak — Encode only during 00:00-08:00 UTC
      /schedule night — Encode only during 20:00-06:00 UTC
      /schedule 02:00-10:00 — Custom UTC window
      /schedule off — Encode immediately (default)
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        current = await get_user_field(user_id, "schedule", "")
        await respond(
            message,
            "**⏰ Encoding Schedule**\n\n"
            f"**Current:** `{current or 'immediate (no schedule)'}`\n\n"
            "**Options:**\n"
            "`/schedule off-peak` — 00:00-08:00 UTC\n"
            "`/schedule night` — 20:00-06:00 UTC\n"
            "`/schedule HH:MM-HH:MM` — Custom UTC window\n"
            "`/schedule off` — Encode immediately"
        )
        return

    value = parts[1].strip().lower()
    if value == "off":
        await update_user_field(user_id, "schedule", "")
        await respond(message, "**Schedule disabled.** Videos will encode immediately.")
    elif value in ("off-peak", "night") or "-" in value:
        await update_user_field(user_id, "schedule", value)
        await respond(message, f"**Schedule set:** `{value}`")
    else:
        await respond(message, "**Invalid schedule.** Use `off-peak`, `night`, `HH:MM-HH:MM`, or `off`.")


# ═══════════════════════════════════════════
# /history — Encoding history
# ═══════════════════════════════════════════

@bot.on_message(filters.command("history", prefixes=TRIGGERS))
async def history_command(client, message):
    """Show recent encoding history."""
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    records = await get_history(user_id, limit=10)
    if not records:
        await respond(message, "**No encoding history found.**")
        return

    text = "**📜 Recent Encodes (last 10)**\n\n"
    for i, rec in enumerate(records, 1):
        orig = humanbytes(rec.get("original_size", 0))
        enc = humanbytes(rec.get("encoded_size", 0))
        name = rec.get("filename", "?")
        res = rec.get("resolution", "?")
        dur = rec.get("duration_secs", 0)
        ts = rec.get("timestamp", "?")[:10]
        text += f"`{i}.` **{name[:30]}** — {res}\n"
        text += f"    {orig} → {enc} | {int(dur)}s | {ts}\n"

    await respond(message, text)


# ═══════════════════════════════════════════
# /autodelete — Toggle auto-delete originals
# ═══════════════════════════════════════════

@bot.on_message(filters.command("autodelete", prefixes=TRIGGERS))
async def autodelete_command(client, message):
    """Toggle auto-delete of original video after encoding."""
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    current = await get_user_field(user_id, "auto_delete", False)
    new_value = not current
    await update_user_field(user_id, "auto_delete", new_value)
    status = "enabled" if new_value else "disabled"
    await respond(message, f"**Auto-delete original messages:** `{status}`")


# ═══════════════════════════════════════════
# /hwaccel — Hardware acceleration toggle
# ═══════════════════════════════════════════

@bot.on_message(filters.command("hwaccel", prefixes=TRIGGERS))
async def hwaccel_command(client, message):
    """Set hardware acceleration mode.

    Usage: /hwaccel <auto|nvenc|vaapi|none>
    """
    user_id = message.from_user.id
    if not await check_user_mdb(user_id):
        return

    parts = (message.text or "").split()
    valid_modes = ("auto", "nvenc", "vaapi", "none")

    if len(parts) < 2:
        current = await get_user_field(user_id, "hw_accel", "auto")
        await respond(
            message,
            "**🖥️ Hardware Acceleration**\n\n"
            f"**Current:** `{current}`\n\n"
            f"**Options:** `{'`, `'.join(valid_modes)}`\n"
            "**Usage:** `/hwaccel nvenc`"
        )
        return

    mode = parts[1].lower()
    if mode not in valid_modes:
        await respond(message, f"**Invalid mode.** Choose from: `{'`, `'.join(valid_modes)}`")
        return

    # Check now whether the requested mode is actually usable on this host,
    # instead of only finding out the next time the user tries to encode.
    if mode in ("nvenc", "vaapi"):
        ok, reason = check_hwaccel_available(mode)
        if not ok:
            await respond(message, f"**Cannot set `{mode}`.**\n{reason}")
            return

    await update_user_field(user_id, "hw_accel", mode)
    await respond(message, f"**Hardware acceleration set to:** `{mode}`")
