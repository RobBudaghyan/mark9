# telegram_notify.py

import requests
import logging

BOT_TOKEN = "<REPLACE_WITH_YOUR_BOT_TOKEN>"
CHAT_ID = "<REPLACE_WITH_YOUR_CHAT_ID>"

# Send a message to Telegram
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        response = requests.post(url, data=data)
        if not response.ok:
            logging.error(f"Telegram failed: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Telegram message: {e}")

# Format message for a trade alert
def format_trade_message(pair, side1, side2, qty1, qty2, price1, price2, reason, balance, pnl=None):
    msg = (
        f"📢 Trade Alert\n"
        f"Pair: {pair}\n"
        f"Action: {reason}\n\n"
        f"Long {qty1:.4f} @ {price1:.6f}\n"
        f"Short {qty2:.4f} @ {price2:.6f}\n\n"
        f"📊 Balance: {balance:.2f} USDT"
    )
    if pnl is not None:
        msg += f"\n💰 PnL: {pnl:.4f}"
    return msg

# Setup Telegram bot command handlers
def setup_telegram_commands(commands):
    # Placeholder for real bot listener logic, e.g., using python-telegram-bot or aiogram
    logging.info("Telegram command listener setup is stubbed in this minimal version")
