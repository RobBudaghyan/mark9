# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# === 🔐 Binance API Keys (from .env) ===
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# === 📲 Telegram Bot Settings (from .env) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === ⚙️ Bot Settings ===
TRADE_CAPITAL_PER_PAIR = 10  # USDT per leg
UPDATE_INTERVAL = 1         # Time between checks in seconds
USE_ISOLATED_MARGIN = False  # Set to True to use Isolated
MAX_CONCURRENT_TRADES = 2    # Set the maximum number of simultaneous trades

# === 📁 File Paths ===
PAIR_CONFIG_CSV = "live_pairs.csv"       # File with live trading pairs + parameters
LOG_FILE = "trade_log.csv"               # Trade execution log
STATE_FILE = "open_positions.json"       # Persistent state to track open trades