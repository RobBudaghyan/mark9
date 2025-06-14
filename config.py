# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# === 🔐 Binance API Keys (loaded from .env) ===
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# === 📲 Telegram Alerts ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === ⚙️ Bot Settings ===
TRADE_CAPITAL_PER_PAIR = 50  # USDT per leg (50 long, 50 short)
UPDATE_INTERVAL = 300  # in seconds (300s = 5 minutes)

# === 📁 File Paths ===
PAIR_CONFIG_CSV = "live_pairs.csv"
LOG_FILE = "trade_log.csv"
