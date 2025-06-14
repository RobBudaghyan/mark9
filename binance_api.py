# binance_api.py (Real-life isolated margin version)

import os
import logging
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET)

def get_pair_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logging.error(f"Price fetch failed for {symbol}: {e}")
        return None

def place_order(symbol, side, quantity, isolated=True):
    try:
        # Margin account must be isolated and enabled for that pair
        response = client.create_margin_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=round(quantity, 6),
            isIsolated='TRUE' if isolated else 'FALSE'
        )
        logging.info(f"✅ Order placed: {side} {quantity} {symbol}")
        return response
    except Exception as e:
        logging.error(f"❌ Order failed: {side} {quantity} {symbol}: {e}")
        return None

def get_margin_balance():
    try:
        balance = client.get_isolated_margin_account()
        return balance['totalAssetOfBtc'], balance
    except Exception as e:
        logging.error(f"❌ Balance fetch failed: {e}")
        return 0, None
