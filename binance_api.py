# binance_api.py

import os
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import BINANCE_API_KEY, BINANCE_API_SECRET

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

assert BINANCE_API_SECRET is not None, "BINANCE_API_SECRET is missing!"


def borrow_asset(symbol, amount_to_borrow, isolated=False):
    """Explicitly borrows an asset, with corrected amount formatting."""
    try:
        asset = symbol.replace("USDT", "")
        # Format the amount to a string with 8 decimal places to prevent float precision errors.
        formatted_amount = f"{amount_to_borrow:.8f}"

        logging.info(f"Attempting to BORROW {formatted_amount} {asset}...")

        loan_receipt = client.create_margin_loan(
            asset=asset,
            amount=formatted_amount,  # Pass the correctly formatted string
            isIsolated=isolated,
            symbol=symbol
        )
        logging.info(f"SUCCESS -> Borrow successful. Transaction ID: {loan_receipt.get('tranId')}")
        return loan_receipt
    except BinanceAPIException as e:
        logging.error(f"FAILED to BORROW {asset}. Code: {e.code}, Message: {e.message}")
        return None


def repay_asset(symbol, amount_to_repay, isolated=False):
    """Explicitly repays a borrowed asset, with corrected amount formatting."""
    try:
        asset = symbol.replace("USDT", "")
        # Format the amount here as well for consistency.
        formatted_amount = f"{amount_to_repay:.8f}"

        logging.info(f"Attempting to REPAY {formatted_amount} {asset}...")

        repay_receipt = client.repay_margin_loan(
            asset=asset,
            amount=formatted_amount,  # Pass the correctly formatted string
            isIsolated=isolated,
            symbol=symbol
        )
        logging.info(f"SUCCESS -> Repay successful. Transaction ID: {repay_receipt.get('tranId')}")
        return repay_receipt
    except BinanceAPIException as e:
        logging.error(f"FAILED to REPAY {asset}. Code: {e.code}, Message: {e.message}")
        return None


def get_pair_price(symbol):
    try:
        return float(client.get_symbol_ticker(symbol=symbol)['price'])
    except Exception as e:
        logging.error(f"Error fetching price for {symbol}: {e}");
        return None


def get_symbol_filters(symbol):
    try:
        info = client.get_symbol_info(symbol)
        return {f['filterType']: f for f in info['filters']}
    except Exception as e:
        logging.error(f"Error fetching filters for {symbol}: {e}");
        return {}


def round_quantity(symbol, qty):
    try:
        filters = get_symbol_filters(symbol)
        step = float(filters.get('LOT_SIZE', {}).get('stepSize', '0.00000001'))
        precision = abs(str(step).find('.') - len(str(step))) - 1
        return round(qty - (qty % step), precision)
    except (ValueError, TypeError):
        return qty


def check_notional(symbol, price, qty):
    filters = get_symbol_filters(symbol)
    min_notional = float(filters.get('MIN_NOTIONAL', {}).get('minNotional', 5.0))
    return price * qty >= min_notional


def place_order(symbol, side, quantity, isolated=False):
    try:
        price = get_pair_price(symbol)
        if price is None: raise Exception("Price unavailable")

        rounded_qty = round_quantity(symbol, quantity)
        notional_value = price * rounded_qty

        logging.info(f"ATTEMPTING TRADE -> {side} {rounded_qty} {symbol} (Value: ~${notional_value:.2f})")

        if not check_notional(symbol, price, rounded_qty):
            logging.error(f"Order REJECTED (local): Notional value ${notional_value:.2f} is below minimum.")
            return None

        order = client.create_margin_order(symbol=symbol, side=side, type='MARKET', quantity=rounded_qty,
                                           isIsolated=isolated)
        logging.info(f"SUCCESS -> Placed {side} order for {rounded_qty} {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"FAILED -> Binance API Error for {symbol}. Code: {e.code}, Message: {e.message}")
        return None
    except Exception as e:
        logging.error(f"FAILED -> Unexpected Error for {symbol}: {e}");
        return None


def get_historical_prices(symbol, window):
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=window)
        return [float(candle[4]) for candle in klines]
    except Exception as e:
        logging.error(f"Error fetching historical prices for {symbol}: {e}");
        return []