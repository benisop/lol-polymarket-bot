"""
config.py — Settings y variables de entorno del Bot D (LoL Polymarket).

Carga desde .env con python-dotenv.
Todos los defaults son seguros: DRY_RUN=true, sin claves reales.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Polymarket ────────────────────────────────────────────────────────────────
POLYMARKET_PRIVATE_KEY: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_PROXY_ADDRESS: str = os.getenv("POLYMARKET_PROXY_ADDRESS", "")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ── LoL Esports API ───────────────────────────────────────────────────────────
LOLESPORTS_BASE_URL: str = os.getenv(
    "LOLESPORTS_BASE_URL", "https://feed.lolesports.com/livestats/v1"
)
LOLESPORTS_SCHEDULE_URL: str = (
    "https://esports-api.lolesports.com/persisted/gw/getSchedule"
)
LEAGUE_IDS: dict = {
    "LCK": "98767991310872058",
    "LEC": "98767991302996019",
}

# ── Risk Management ───────────────────────────────────────────────────────────
BANKROLL: float = float(os.getenv("BANKROLL", "1000"))
MIN_EDGE_THRESHOLD: float = float(os.getenv("MIN_EDGE_THRESHOLD", "0.08"))
MAX_POSITION_SIZE_USD: float = float(os.getenv("MAX_POSITION_SIZE_USD", "50"))
MIN_MARKET_LIQUIDITY: float = float(os.getenv("MIN_MARKET_LIQUIDITY", "50"))
MAX_OPEN_POSITIONS: int = 3
STOP_LOSS_PCT: float = 0.15       # 15% del bankroll diario
KELLY_FRACTION: float = 0.25      # Kelly fraccionado al 25%
MAX_GAME_MINUTE: int = 25         # no operar después del minuto 25

# ── Operación ─────────────────────────────────────────────────────────────────
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
SCHEDULER_INTERVAL_SECONDS: int = 300   # 5 minutos

# ── Rutas ─────────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "lol_bot.db")
MODEL_PATH: str = os.getenv("MODEL_PATH", "backend/model/model.pkl")
