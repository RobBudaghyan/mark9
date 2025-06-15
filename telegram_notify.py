# telegram_notify.py

import requests
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(message):
    """Sends a message to the configured Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram token or chat ID is not set. Skipping message.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info("Successfully sent Telegram message.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Telegram message: {e}")


def format_trade_message(pair, side1, side2, qty1, qty2, price1, price2, reason, pnl=None):
    """
    Formats a trade message for Telegram.
    This new version matches the arguments sent by the bot.
    """
    msg = (
        f"*Trade Alert*\n\n"
        f"*Pair*: `{pair}`\n"
        f"*Action*: `{reason}`\n\n"
        f"*Leg 1*: {side1} `{qty1:.4f}` @ `{price1:.6f}`\n"
        f"*Leg 2*: {side2} `{qty2:.4f}` @ `{price2:.6f}`\n"
    )
    if pnl is not None:
        pnl_str = f"+${pnl:.4f}" if pnl >= 0 else f"-${abs(pnl):.4f}"
        msg += f"\n*PnL*: `{pnl_str}`"
    return msg