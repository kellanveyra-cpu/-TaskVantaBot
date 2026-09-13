"""
TaskVanta - Configuration loader
Reads all settings from environment variables (see .env.example).
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_admin_ids() -> set:
    raw = os.getenv("ADMIN_IDS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


# --- Required ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# --- Admin access ---
ADMIN_IDS: set = _get_admin_ids()

# --- Bot identity (used to build referral links: https://t.me/<username>?start=<id>) ---
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "").lstrip("@")

# --- Database ---
# On Railway, mount a Volume and point this at it (e.g. /data/taskvanta.db)
# so the database survives redeploys. See README for details.
DB_PATH: str = os.getenv("DB_PATH", "taskvanta.db")

# --- Economy settings ---
DEFAULT_TASK_REWARD: float = float(os.getenv("DEFAULT_TASK_REWARD", "1.0"))
REFERRAL_REWARD: float = float(os.getenv("REFERRAL_REWARD", "10.0"))
MIN_WITHDRAWAL: float = float(os.getenv("MIN_WITHDRAWAL", "130.0"))

# --- Branding / demo notice ---
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "TaskVanta")
DEMO_MODE: bool = _get_bool("DEMO_MODE", True)

DEMO_BANNER = (
    "⚠️ <b>DEMO / TEST ENVIRONMENT</b> ⚠️\n"
    "This bot does not process real money. All balances, tasks and "
    "withdrawals are simulated for demonstration purposes only."
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
