# binance_api.py

import os
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import BINANCE_API_KEY, BINANCE_API_SECRET
from config import USE_ISOLATED_MARGIN

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

def get_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                return step_size
    except Exception as e:
        logging.error(f"Error fetching step size for {symbol}: {e}")
    return 0.001  # fallback

def round_quantity(symbol, qty):
    step = get_step_size(symbol)
    return round(qty - (qty % step), 8)

def get_symbol_filters(symbol):
    try:
        info = client.get_symbol_info(symbol)
        filters = {}
        for f in info['filters']:
            filters[f['filterType']] = f
        return filters
    except Exception as e:
        logging.error(f"Error fetching filters for {symbol}: {e}")
        return {}

def round_quantity(symbol, qty):
    filters = get_symbol_filters(symbol)
    step = float(filters.get('LOT_SIZE', {}).get('stepSize', 0.001))
    return round(qty - (qty % step), 8)

def check_notional(symbol, price, qty):
    filters = get_symbol_filters(symbol)
    min_notional = float(filters.get('MIN_NOTIONAL', {}).get('minNotional', 5.0))
    return price * qty >= min_notional

def place_order(symbol, side, quantity, isolated=True):
    try:
        price = get_pair_price(symbol)
        if price is None:
            raise Exception("Price unavailable")

        rounded_qty = round_quantity(symbol, quantity)

        if not check_notional(symbol, price, rounded_qty):
            logging.error(f"Order skipped: Notional too small for {symbol} (price={price}, qty={rounded_qty})")
            return None


        order = client.create_margin_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=rounded_qty,
            isIsolated=USE_ISOLATED_MARGIN
        )

        logging.info(f"[Live] Placed {side} order for {rounded_qty} {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Order failed: {e.message}")
        return None
    except Exception as e:
        logging.error(f"Order error: {e}")
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
