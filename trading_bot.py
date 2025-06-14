# trading_bot.py

import time
import pandas as pd
import logging
import threading
import json
from binance_api import get_pair_price, place_order, get_margin_balance, get_historical_prices
from telegram_notify import send_telegram_message, format_trade_message, setup_telegram_commands
from config import PAIR_CONFIG_CSV, TRADE_CAPITAL_PER_PAIR, UPDATE_INTERVAL, LOG_FILE, STATE_FILE
from config import USE_ISOLATED_MARGIN

logging.basicConfig(level=logging.INFO)

open_positions = {}
abort_flag = threading.Event()

def load_pair_configs():
    return pd.read_csv(PAIR_CONFIG_CSV).to_dict(orient='records')

def zscore(series):
    std = series.std()
    if std == 0 or pd.isna(std):
        return 0
    return (series.iloc[-1] - series.mean()) / std

def log_trade(sym1, sym2, side1, side2, price1, price2, qty1, qty2, action, pnl=None):
    now = pd.Timestamp.now()
    log_row = pd.DataFrame([{
        'timestamp': now,
        'sym1': sym1,
        'sym2': sym2,
        'side1': side1,
        'side2': side2,
        'price1': price1,
        'price2': price2,
        'qty1': qty1,
        'qty2': qty2,
        'action': action,
        'pnl': pnl
    }])
    try:
        log_row.to_csv(LOG_FILE, mode='a', header=not pd.io.common.file_exists(LOG_FILE), index=False)
    except Exception as e:
        logging.error(f"Logging failed: {e}")

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(open_positions, f, default=str)

def load_state():
    global open_positions
    try:
        with open(STATE_FILE, 'r') as f:
            open_positions = json.load(f)
    except FileNotFoundError:
        open_positions = {}

def bot_commands():
    def status():
        bal = get_margin_balance()
        msg = f"📊 Bot Status\nPositions: {len(open_positions)}\nTotal Net Asset: {bal.get('totalNetAssetOfBtc', 'N/A')} BTC\nAssets: {bal.get('userAssets', [])}"
        send_telegram_message(msg)

    def abort():
        abort_flag.set()
        send_telegram_message("⛔️ Bot aborted by user.")

    setup_telegram_commands({
        '/status': status,
        '/abort': abort
    })

def run_bot():
    logging.info("🚀 Live Trading Bot Started")
    bot_commands()
    load_state()
    pair_configs = load_pair_configs()
    logging.info(f"✅ Loaded {len(pair_configs)} pairs from config")

    while not abort_flag.is_set():
        for pair in pair_configs:
            sym1, sym2 = pair['sym1'], pair['sym2']
            key = f"{sym1}-{sym2}"
            window = int(pair['window'])
            z_entry = float(pair['z_entry'])
            z_exit = float(pair['z_exit'])
            stop_loss = float(pair.get('stop_loss', 0.05))
            take_profit = float(pair.get('take_profit', 0.05))

            prices1 = get_historical_prices(sym1, window)
            prices2 = get_historical_prices(sym2, window)
            if prices1 is None or prices2 is None:
                continue

            spread_series = pd.Series([p1 - p2 for p1, p2 in zip(prices1, prices2)])
            price1, price2 = prices1[-1], prices2[-1]
            z = zscore(spread_series)
            logging.info(f"🔍 Checking pair {sym1}-{sym2}, z = {z:.3f}")

            if key not in open_positions:
                if z > z_entry or z < -z_entry:
                    direction = 'SELL SPREAD' if z > z_entry else 'BUY SPREAD'
                    side1, side2 = ('SELL', 'BUY') if z > z_entry else ('BUY', 'SELL')
                    qty1 = TRADE_CAPITAL_PER_PAIR / price1
                    qty2 = TRADE_CAPITAL_PER_PAIR / price2

                    res1 = place_order(sym1, side1, qty1, isolated=USE_ISOLATED_MARGIN)
                    res2 = place_order(sym2, side2, qty2, isolated=USE_ISOLATED_MARGIN)

                    if not res1 or not res2:
                        if res1:
                            reverse_side = 'BUY' if side1 == 'SELL' else 'SELL'
                            place_order(sym1, reverse_side, qty1, isolated=USE_ISOLATED_MARGIN)
                        if res2:
                            reverse_side = 'BUY' if side2 == 'SELL' else 'SELL'
                            place_order(sym2, reverse_side, qty2, isolated=USE_ISOLATED_MARGIN)
                        continue

                    open_positions[key] = {
                        'sym1': sym1, 'sym2': sym2,
                        'qty1': qty1, 'qty2': qty2,
                        'price1': price1, 'price2': price2,
                        'direction': direction,
                        'stop_loss': stop_loss, 'take_profit': take_profit
                    }
                    save_state()
                    balance = float(get_margin_balance()['totalNetAssetOfBtc']) * price1
                    msg = format_trade_message(f"{sym1}/{sym2}", side1, side2, round(qty1, 4), round(qty2, 4), price1, price2, direction, balance)
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, side1, side2, price1, price2, qty1, qty2, direction)

            else:
                pos = open_positions[key]
                direction = pos['direction']
                if direction == 'BUY SPREAD':
                    pnl1 = (price1 - pos['price1']) * pos['qty1']
                    pnl2 = (pos['price2'] - price2) * pos['qty2']
                else:
                    pnl1 = (pos['price1'] - price1) * pos['qty1']
                    pnl2 = (price2 - pos['price2']) * pos['qty2']
                current_pnl = pnl1 + pnl2
                entry_value = pos['price1'] * pos['qty1'] + pos['price2'] * pos['qty2']
                pnl_pct = current_pnl / entry_value

                exit_condition = False
                reason = ""

                if direction == 'SELL SPREAD' and z < z_exit:
                    exit_condition = True
                    reason = "CLOSE SELL SPREAD (Z Exit)"
                elif direction == 'BUY SPREAD' and z > -z_exit:
                    exit_condition = True
                    reason = "CLOSE BUY SPREAD (Z Exit)"
                elif pnl_pct <= -pos['stop_loss']:
                    exit_condition = True
                    reason = "STOP LOSS"
                elif pnl_pct >= pos['take_profit']:
                    exit_condition = True
                    reason = "TAKE PROFIT"

                if exit_condition:
                    side1 = "BUY" if direction == "SELL SPREAD" else "SELL"
                    side2 = "SELL" if direction == "SELL SPREAD" else "BUY"
                    balance = float(get_margin_balance()['totalNetAssetOfBtc']) * price1
                    msg = format_trade_message(f"{sym1}/{sym2}", side1 + " (close)", side2 + " (close)", pos['qty1'], pos['qty2'], price1, price2, reason, balance, current_pnl)
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, side1, side2, price1, price2, pos['qty1'], pos['qty2'], reason, current_pnl)
                    del open_positions[key]
                    save_state()

        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    run_bot()
