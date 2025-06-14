# trading_bot.py

import time
import pandas as pd
import logging
from binance_api import get_pair_price, place_order, get_margin_balance
from telegram_notify import send_telegram_message, format_trade_message
from config import PAIR_CONFIG_CSV, TRADE_CAPITAL_PER_PAIR, UPDATE_INTERVAL, LOG_FILE

logging.basicConfig(level=logging.INFO)

open_positions = {}

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

def run_bot():
    logging.info("🚀 Live Trading Bot Started")
    pair_configs = load_pair_configs()
    logging.info(f"✅ Loaded {len(pair_configs)} pairs from config")

    while True:
        for pair in pair_configs:
            sym1, sym2 = pair['sym1'], pair['sym2']
            key = f"{sym1}-{sym2}"
            window = int(pair['window'])
            z_entry = float(pair['z_entry'])
            z_exit = float(pair['z_exit'])
            stop_loss = float(pair.get('stop_loss', 0.05))
            take_profit = float(pair.get('take_profit', 0.05))

            price1 = get_pair_price(sym1)
            price2 = get_pair_price(sym2)
            if price1 is None or price2 is None:
                continue

            spread_series = pd.Series([price1 - price2] * window)
            z = zscore(spread_series)
            logging.info(f"🔍 Checking pair {sym1}-{sym2}, z = {z:.3f}")

            if key not in open_positions:
                if z > z_entry:
                    qty1 = TRADE_CAPITAL_PER_PAIR / price1
                    qty2 = TRADE_CAPITAL_PER_PAIR / price2
                    place_order(sym1, 'SELL', qty1, isolated=True)
                    place_order(sym2, 'BUY', qty2, isolated=True)
                    open_positions[key] = {
                        'sym1': sym1, 'sym2': sym2,
                        'qty1': qty1, 'qty2': qty2,
                        'price1': price1, 'price2': price2,
                        'direction': 'SELL SPREAD',
                        'stop_loss': stop_loss, 'take_profit': take_profit
                    }
                    balance = float(get_margin_balance()['totalNetAssetOfBtc']) * price1
                    msg = format_trade_message(f"{sym1}/{sym2}", "Short", "Long", round(qty1, 4), round(qty2, 4), price1, price2, "SELL SPREAD", balance)
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, "Short", "Long", price1, price2, qty1, qty2, "SELL SPREAD")

                elif z < -z_entry:
                    qty1 = TRADE_CAPITAL_PER_PAIR / price1
                    qty2 = TRADE_CAPITAL_PER_PAIR / price2
                    place_order(sym1, 'BUY', qty1, isolated=True)
                    place_order(sym2, 'SELL', qty2, isolated=True)
                    open_positions[key] = {
                        'sym1': sym1, 'sym2': sym2,
                        'qty1': qty1, 'qty2': qty2,
                        'price1': price1, 'price2': price2,
                        'direction': 'BUY SPREAD',
                        'stop_loss': stop_loss, 'take_profit': take_profit
                    }
                    balance = float(get_margin_balance()['totalNetAssetOfBtc']) * price1
                    msg = format_trade_message(f"{sym1}/{sym2}", "Long", "Short", round(qty1, 4), round(qty2, 4), price1, price2, "BUY SPREAD", balance)
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, "Long", "Short", price1, price2, qty1, qty2, "BUY SPREAD")

            else:
                pos = open_positions[key]
                # Calculate PnL for dynamic SL/TP
                current_pnl = (price1 - pos['price1']) * pos['qty1'] + (pos['price2'] - price2) * pos['qty2']
                entry_value = pos['price1'] * pos['qty1'] + pos['price2'] * pos['qty2']
                pnl_pct = current_pnl / entry_value

                exit_condition = False

                if pos['direction'] == 'SELL SPREAD' and z < z_exit:
                    exit_condition = True
                    reason = "CLOSE SELL SPREAD (Z Exit)"
                elif pos['direction'] == 'BUY SPREAD' and z > -z_exit:
                    exit_condition = True
                    reason = "CLOSE BUY SPREAD (Z Exit)"
                elif pnl_pct <= -pos['stop_loss']:
                    exit_condition = True
                    reason = "STOP LOSS"
                elif pnl_pct >= pos['take_profit']:
                    exit_condition = True
                    reason = "TAKE PROFIT"

                if exit_condition:
                    side1 = "BUY" if pos['direction'] == "SELL SPREAD" else "SELL"
                    side2 = "SELL" if pos['direction'] == "SELL SPREAD" else "BUY"
                    balance = float(get_margin_balance()['totalNetAssetOfBtc']) * price1
                    msg = format_trade_message(f"{sym1}/{sym2}", side1 + " (close)", side2 + " (close)", pos['qty1'], pos['qty2'], price1, price2, reason, balance, current_pnl)
                    send_telegram_message(msg)
                    log_trade(sym1, sym2, side1, side2, price1, price2, pos['qty1'], pos['qty2'], reason, current_pnl)
                    del open_positions[key]

        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    run_bot()
