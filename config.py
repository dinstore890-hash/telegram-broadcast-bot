import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot ───────────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# ── Admin ─────────────────────────────────────────────────────────────────────
_raw_admins = os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "0"))
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]

# ── Telethon MTProto ──────────────────────────────────────────────────────────
_raw_api_id = os.getenv("API_ID", "0")
API_ID: int = int(_raw_api_id) if _raw_api_id.isdigit() else 0
API_HASH: str = os.getenv("API_HASH", "")
PHONE_NUMBER: str = os.getenv("PHONE_NUMBER", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/broadcast.db")
SESSION_DIR: str = os.getenv("SESSION_DIR", "sessions")
LOG_DIR: str = os.getenv("LOG_DIR", "logs")

# ── Broadcast ─────────────────────────────────────────────────────────────────
BROADCAST_DELAY: float = float(os.getenv("BROADCAST_DELAY", "7.0"))
TEST_MODE: bool = os.getenv("TEST_MODE", "false").lower() == "true"

# ── QRIS ────────────────────────────────────────────────────────────────────
QRIS_FILE_ID: str = os.getenv("QRIS_FILE_ID", "")

# ── Validasi wajib ────────────────────────────────────────────────────────────
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan di .env")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS tidak ditemukan di .env")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
