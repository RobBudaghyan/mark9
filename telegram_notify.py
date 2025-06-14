# telegram_notify.py

import requests
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logging.error(f"Telegram failed: {response.text}")
    except Exception as e:
        logging.error(f"Telegram error: {e}")

def format_trade_message(pair, side1, side2, qty1, qty2, price1, price2, action, balance, pnl=None):
    msg = f"<b>📢 Trade Alert</b>\n"
    msg += f"Pair: <code>{pair}</code>\n"
    msg += f"Action: <b>{action}</b>\n\n"
    msg += f"{side1} {qty1} @ {price1}\n{side2} {qty2} @ {price2}\n"
    if pnl is not None:
        msg += f"\n💰 <b>Estimated PnL:</b> {pnl:.2f} USDT"
    msg += f"\n📊 <i>Balance:</i> {balance:.2f} USDT"
    return msg
