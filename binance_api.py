# binance_api.py

import os
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import BINANCE_API_KEY, BINANCE_API_SECRET

# # Load keys from environment variables
# API_KEY = os.getenv("BINANCE_API_KEY")
# API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

assert BINANCE_API_SECRET is not None, "BINANCE_API_SECRET is missing!"


# Get live price of a symbol
def get_pair_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logging.error(f"Error fetching price for {symbol}: {e}")
        return None

# Get margin balance for isolated margin
def get_margin_balance():
    try:
        return client.get_isolated_margin_account()
    except Exception as e:
        logging.error(f"Error fetching margin balance: {e}")
        return {}

# Place order in isolated margin mode
def place_order(symbol, side, quantity, isolated=True):
    try:
        order = client.create_margin_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=round(quantity, 6),
            isIsolated=isolated
        )
        logging.info(f"[Live] Placed {side} order for {quantity} {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Order failed: {e.message}")
        return None

# Get historical prices for z-score calculation
def get_historical_prices(symbol, window):
    try:
        klines = client.get_klines(
            symbol=symbol,
            interval=Client.KLINE_INTERVAL_1MINUTE,
            limit=window
        )
        return [float(candle[4]) for candle in klines]  # close prices
    except Exception as e:
        logging.error(f"Error fetching historical prices for {symbol}: {e}")
        return []
