# trading_bot.py

import time
import pandas as pd
import logging
import threading
import json
from binance_api import get_pair_price, place_order, get_historical_prices, borrow_asset, repay_asset
from telegram_notify import send_telegram_message, format_trade_message
from config import PAIR_CONFIG_CSV, TRADE_CAPITAL_PER_PAIR, UPDATE_INTERVAL, LOG_FILE, STATE_FILE, USE_ISOLATED_MARGIN, \
    MAX_CONCURRENT_TRADES

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("binance").setLevel(logging.WARNING)

open_positions = {}
abort_flag = threading.Event()


def load_pair_configs():
    try:
        return pd.read_csv(PAIR_CONFIG_CSV).to_dict(orient='records')
    except FileNotFoundError:
        logging.error(f"{PAIR_CONFIG_CSV} not found.");
        return []


def zscore(series):
    std = series.std()
    if std == 0 or pd.isna(std): return 0
    return (series.iloc[-1] - series.mean()) / std


def log_trade(sym1, sym2, side1, side2, price1, price2, qty1, qty2, action, pnl=None):
    now = pd.Timestamp.now()
    columns = ['timestamp', 'sym1', 'sym2', 'side1', 'side2', 'price1', 'price2', 'qty1', 'qty2', 'action', 'pnl']
    log_row = pd.DataFrame(
        [{'timestamp': now, 'sym1': sym1, 'sym2': sym2, 'side1': side1, 'side2': side2, 'price1': price1,
          'price2': price2, 'qty1': qty1, 'qty2': qty2, 'action': action, 'pnl': pnl}])
    try:
        log_row.to_csv(LOG_FILE, mode='a', header=not pd.io.common.file_exists(LOG_FILE), index=False)
    except Exception as e:
        logging.error(f"Logging failed: {e}")


def save_state():
    with open(STATE_FILE, 'w') as f: json.dump(open_positions, f, indent=4)


def load_state():
    global open_positions
    try:
        with open(STATE_FILE, 'r') as f:
            open_positions = json.load(f)
        logging.info(f"Loaded {len(open_positions)} positions from state.")
    except FileNotFoundError:
        open_positions = {};
        logging.info("No state file found, starting fresh.")


def run_bot():
    logging.info("🚀 Live Trading Bot Started")
    load_state()

    while not abort_flag.is_set():
        pair_configs = load_pair_configs()
        if not pair_configs: time.sleep(60); continue

        # --- MANAGE ALL OPEN POSITIONS ---
        for key in list(open_positions.keys()):
            pos = open_positions.get(key)
            if not pos: continue

            sym1, sym2, direction = pos['sym1'], pos['sym2'], pos['direction']
            pair_config = next((p for p in pair_configs if f"{p['sym1']}/{p['sym2']}" == key), None)
            if not pair_config:
                logging.error(f"Config for open position {key} not found. Cannot manage.");
                continue

            prices1 = get_historical_prices(sym1, int(pair_config['window']))
            prices2 = get_historical_prices(sym2, int(pair_config['window']))
            if not prices1 or not prices2: continue

            price1, price2 = prices1[-1], prices2[-1]
            spread_series = pd.Series([p1 / p2 for p1, p2 in zip(prices1, prices2)])
            z = zscore(spread_series)

            # This log will now always show the Z-score for any open positions
            logging.info(f"✅ Managing position {key}, z = {z:.3f}")

            entry_p1, entry_p2, qty1, qty2 = map(float, [pos['price1'], pos['price2'], pos['qty1'], pos['qty2']])
            pnl1 = (price1 - entry_p1) * qty1 if direction == 'BUY SPREAD' else (entry_p1 - price1) * qty1
            pnl2 = (entry_p2 - price2) * qty2 if direction == 'BUY SPREAD' else (price2 - entry_p2) * qty2
            current_pnl = pnl1 + pnl2
            entry_value = (entry_p1 * qty1) + (entry_p2 * qty2)
            pnl_pct = current_pnl / entry_value if entry_value != 0 else 0
            logging.info(f"Position PnL: {current_pnl:.4f} USD ({pnl_pct:+.2%})")

            exit_condition, reason = False, ""
            z_exit, stop_loss, take_profit = map(float, [pair_config['z_exit'], pos['stop_loss'], pos['take_profit']])

            # *** BUG FIX: Corrected the exit logic for BUY SPREAD ***
            if (direction == 'SELL SPREAD' and z < z_exit) or (direction == 'BUY SPREAD' and z > -z_exit):
                exit_condition, reason = True, f"Z-Score Exit ({z:.2f})"
            elif pnl_pct <= -stop_loss:
                exit_condition, reason = True, f"Stop Loss ({-stop_loss:.2%})"
            elif pnl_pct >= take_profit:
                exit_condition, reason = True, f"Take Profit ({take_profit:.2%})"

            if exit_condition:
                logging.info(f"Exit condition '{reason}' met for {key}. Closing position.")

                side1_close = "BUY" if direction == "SELL SPREAD" else "SELL"
                side2_close = "SELL" if direction == "SELL SPREAD" else "BUY"

                res1 = place_order(sym1, side1_close, qty1, isolated=USE_ISOLATED_MARGIN)
                res2 = place_order(sym2, side2_close, qty2, isolated=USE_ISOLATED_MARGIN)

                if direction == "SELL SPREAD" and res1:
                    repay_qty = float(res1['fills'][0]['qty']);
                    repay_asset(sym1, repay_qty, isolated=USE_ISOLATED_MARGIN)
                if direction == "BUY SPREAD" and res2:
                    repay_qty = float(res2['fills'][0]['qty']);
                    repay_asset(sym2, repay_qty, isolated=USE_ISOLATED_MARGIN)

                msg = format_trade_message(key, side1_close, side2_close, qty1, qty2, price1, price2,
                                           f"CLOSE: {reason}", current_pnl)
                send_telegram_message(msg)
                log_trade(sym1, sym2, side1_close, side2_close, price1, price2, qty1, qty2, f"CLOSE: {reason}",
                          current_pnl)

                del open_positions[key]
                save_state()

        # --- LOOK FOR NEW TRADES IF BELOW THE CONCURRENT LIMIT ---
        if len(open_positions) < MAX_CONCURRENT_TRADES:
            for pair in pair_configs:
                if len(open_positions) >= MAX_CONCURRENT_TRADES: break

                sym1, sym2 = pair['sym1'], pair['sym2']
                key = f"{sym1}/{sym2}"
                if key in open_positions: continue

                prices1 = get_historical_prices(sym1, int(pair['window']))
                prices2 = get_historical_prices(sym2, int(pair['window']))
                if not prices1 or not prices2: continue

                price1, price2 = prices1[-1], prices2[-1]
                spread_series = pd.Series([p1 / p2 for p1, p2 in zip(prices1, prices2)])
                z = zscore(spread_series)

                # *** NEW LOGGING: Always print the Z-score for every pair ***
                logging.info(f"🔍 Checking pair {key}, z = {z:.3f}")

                if abs(z) > float(pair['z_entry']):
                    direction = 'SELL SPREAD' if z > 0 else 'BUY SPREAD'
                    logging.info(f"Entry signal for {key}. Direction: {direction}.")

                    qty1, qty2 = TRADE_CAPITAL_PER_PAIR / price1, TRADE_CAPITAL_PER_PAIR / price2

                    if direction == 'SELL SPREAD':
                        if not (borrow_asset(sym1, qty1, isolated=USE_ISOLATED_MARGIN)): continue
                        if not (res1 := place_order(sym1, "SELL", qty1, isolated=USE_ISOLATED_MARGIN)): repay_asset(
                            sym1, qty1, isolated=USE_ISOLATED_MARGIN); continue
                        if not (res2 := place_order(sym2, "BUY", qty2, isolated=USE_ISOLATED_MARGIN)): place_order(sym1,
                                                                                                                   "BUY",
                                                                                                                   qty1,
                                                                                                                   isolated=USE_ISOLATED_MARGIN); repay_asset(
                            sym1, qty1, isolated=USE_ISOLATED_MARGIN); continue
                    else:  # BUY SPREAD
                        if not (borrow_asset(sym2, qty2, isolated=USE_ISOLATED_MARGIN)): continue
                        if not (res1 := place_order(sym1, "BUY", qty1, isolated=USE_ISOLATED_MARGIN)): repay_asset(sym2,
                                                                                                                   qty2,
                                                                                                                   isolated=USE_ISOLATED_MARGIN); continue
                        if not (res2 := place_order(sym2, "SELL", qty2, isolated=USE_ISOLATED_MARGIN)): place_order(
                            sym1, "SELL", qty1, isolated=USE_ISOLATED_MARGIN); repay_asset(sym2, qty2,
                                                                                           isolated=USE_ISOLATED_MARGIN); continue

                    qty1, price1 = float(res1['fills'][0]['qty']), float(res1['fills'][0]['price'])
                    qty2, price2 = float(res2['fills'][0]['qty']), float(res2['fills'][0]['price'])

                    open_positions[key] = {'sym1': sym1, 'sym2': sym2, 'qty1': qty1, 'price1': price1, 'qty2': qty2,
                                           'price2': price2, 'direction': direction,
                                           'stop_loss': pair.get('stop_loss', 0.05),
                                           'take_profit': pair.get('take_profit', 0.05)}
                    save_state()

                    msg = format_trade_message(key, direction.split()[0], direction.split()[1], qty1, qty2, price1,
                                               price2, "OPEN")
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, direction.split()[0], direction.split()[1], price1, price2, qty1, qty2,
                              "OPEN")
                    logging.info(f"✅ Successfully opened position for {key}.")

        time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    run_bot()