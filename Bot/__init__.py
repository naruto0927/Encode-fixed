import os
import sys
import logging

from dotenv import load_dotenv
from pyrogram import Client

# Load variables from a local .env file into the process environment.
# IMPORTANT: this does NOT override a variable that's already set in the
# real environment (e.g. exported in your shell, or injected by Docker/
# Heroku/systemd) -- real env vars always win, .env only fills in what's
# missing. This is what was silently broken before: nothing ever read
# .env at all, so values there were ignored in favor of whatever (if
# anything) happened to already be in the environment.
load_dotenv()

if os.path.exists("error.log"):
    os.remove("error.log")

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("error.log"), logging.StreamHandler()],
)
LOG = logging.getLogger("Erika-Amano")
# Pyrogram is fairly chatty at INFO (session/connection churn); keep our own
# log clean while still surfacing warnings/errors from the library.
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ─── Environment Variables ───
LOG.info("Checking Bot Variables...")

TRIGGERS = os.environ.get("TRIGGERS", "/ !").split(" ")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
MONGO_DB = os.environ.get("MONGO_DB", "")
FILES_CHANNEL = int(os.environ.get("FILES_CHANNEL", 0))
BOT_NAME = os.environ.get("BOT_NAME", "Erika")
# NOTE: this must be a Pyrogram-format session string. Telethon's
# StringSession output is NOT compatible with Pyrogram -- see Readme.MD for
# how to generate a fresh one for this version of the bot.
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ─── New feature env vars ───
AUTO_AUTH = os.environ.get("AUTO_AUTH", "false").lower() in ("true", "1", "yes")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", 1))
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 0))  # bytes, 0 = unlimited
DAILY_QUOTA = int(os.environ.get("DAILY_QUOTA", 0))  # 0 = unlimited
NOTIFICATION_CHANNEL = int(os.environ.get("NOTIFICATION_CHANNEL", 0))
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "")
WATERMARK_IMAGE = os.environ.get("WATERMARK_IMAGE", "")  # path to overlay image
HW_ACCEL = os.environ.get("HW_ACCEL", "auto")  # auto, nvenc, vaapi, none

# ─── Validate required vars ───
_missing = []
if not BOT_TOKEN:
    _missing.append("BOT_TOKEN")
if not API_ID:
    _missing.append("API_ID")
if not API_HASH:
    _missing.append("API_HASH")
if not OWNER_ID:
    _missing.append("OWNER_ID")
if not MONGO_DB:
    _missing.append("MONGO_DB")

if _missing:
    LOG.critical(f"Missing required environment variables: {', '.join(_missing)}")
    sys.exit(1)

# ─── Create dirs ───
os.makedirs("downloads", exist_ok=True)

# ─── Bot client (connected in __main__.py) ───
# workdir="." keeps the .session file next to the rest of the bot's runtime
# files (matches where the old Telethon .session file used to land).
bot = Client(
    "ErikaBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir=".",
)

# ─── Optional userbot for large (>2GB) uploads ───
# May be reset to None in __main__.py if the session string fails to connect
# -- see the comment there for why plugins should treat `ubot` as "maybe None
# even though it was truthy at import time" is NOT the case: by the time
# plugins are imported, connection has already been attempted and this value
# is final.
ubot = None
if SESSION_STRING:
    ubot = Client(
        "ErikaUser",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        workdir=".",
    )
