# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# === 🔐 Binance API Keys (from .env) ===
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# === 📲 Telegram Bot Settings ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === ⚙️ Bot Settings ===
TRADE_CAPITAL_PER_PAIR = 50  # USDT per leg
UPDATE_INTERVAL = 60       # Time between checks in seconds (e.g., 300 = 5min)

# === 📁 File Paths ===
PAIR_CONFIG_CSV = "live_pairs.csv"       # File with live trading pairs + parameters
LOG_FILE = "trade_log.csv"               # Trade execution log
STATE_FILE = "open_positions.json"       # Persistent state to track open trades
