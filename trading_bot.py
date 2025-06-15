# trading_bot.py

import time
import pandas as pd
import logging
import threading
import json
from binance_api import get_pair_price, place_order, get_historical_prices, borrow_asset, repay_asset
from telegram_notify import send_telegram_message, format_trade_message, get_updates
from config import PAIR_CONFIG_CSV, TRADE_CAPITAL_PER_PAIR, UPDATE_INTERVAL, LOG_FILE, STATE_FILE, USE_ISOLATED_MARGIN, \
    MAX_CONCURRENT_TRADES, TELEGRAM_CHAT_ID

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("binance").setLevel(logging.WARNING)

open_positions = {}
abort_flag = threading.Event()
last_update_id = 0


def clear_pending_updates():
    """
    Clears any messages sent to the bot while it was offline by fetching all
    pending updates and marking them as read.
    """
    global last_update_id
    try:
        logging.info("Attempting to clear pending Telegram updates...")
        # A short timeout will fetch all readily available updates.
        # The offset of -1 can also be used to get the last confirmed update.
        updates = get_updates(offset=-1, timeout=1)
        if updates:
            last_update_id = updates[-1]['update_id']
            logging.info(f"Pending updates cleared. Last update ID processed: {last_update_id}.")
        else:
            logging.info("No pending updates to clear.")
    except Exception as e:
        logging.error(f"Failed to clear pending Telegram updates: {e}")


def handle_telegram_commands():
    """Polls for and handles incoming Telegram commands from the authorized chat."""
    global last_update_id
    logging.info("Telegram command handler started.")

    try:
        authorized_chat_id = int(TELEGRAM_CHAT_ID)
    except (ValueError, TypeError):
        logging.error("TELEGRAM_CHAT_ID is not set or invalid in config.py. Command handler will not start.")
        return

    while not abort_flag.is_set():
        try:
            # Poll for new updates using the last known update_id
            updates = get_updates(offset=last_update_id + 1, timeout=5)
            if updates:
                for update in updates:
                    last_update_id = update['update_id']

                    message = update.get('message')
                    if not message:
                        continue

                    # SECURITY: Only process messages from the authorized chat ID
                    message_chat_id = message.get('chat', {}).get('id')
                    if message_chat_id != authorized_chat_id:
                        logging.warning(f"Ignoring message from unauthorized chat ID: {message_chat_id}")
                        continue

                    if message.get('text'):
                        text = message['text'].strip()
                        if text == '/status':
                            if not open_positions:
                                status_msg = "Bot is running. No open positions."
                            else:
                                status_msg = "Bot is running. Open positions:\n\n"
                                for key, pos in open_positions.items():
                                    status_msg += (
                                        f"*Pair*: `{key}`\n"
                                        f"  - *Direction*: {pos['direction']}\n"
                                        f"  - *Qty 1*: {float(pos['qty1']):.4f} {pos['sym1']}\n"
                                        f"  - *Qty 2*: {float(pos['qty2']):.4f} {pos['sym2']}\n"
                                        f"  - *Entry Price 1*: {float(pos['price1']):.6f}\n"
                                        f"  - *Entry Price 2*: {float(pos['price2']):.6f}\n\n"
                                    )
                            send_telegram_message(status_msg)
                        elif text == '/abort':
                            send_telegram_message("🛑 Abort command received. Shutting down gracefully...")
                            logging.info("Abort command received via Telegram. Shutting down.")
                            abort_flag.set()
                            break  # Exit inner loop
            if abort_flag.is_set():
                break  # Exit outer loop
        except Exception as e:
            logging.error(f"Error in Telegram command handler: {e}", exc_info=True)
            time.sleep(10)  # Wait longer after an error


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
    log_row = pd.DataFrame(
        [{'timestamp': now, 'sym1': sym1, 'sym2': sym2, 'side1': side1, 'side2': side2,
          'price1': price1, 'price2': price2, 'qty1': qty1, 'qty2': qty2, 'action': action, 'pnl': pnl}])
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
    send_telegram_message("🚀 *Bot started successfully!*")
    load_state()

    # CRITICAL: Clear any old commands before starting the handler
    clear_pending_updates()

    command_thread = threading.Thread(target=handle_telegram_commands, daemon=True)
    command_thread.start()

    while not abort_flag.is_set():
        try:
            pair_configs = load_pair_configs()
            if not pair_configs:
                time.sleep(60)
                continue

            # --- MANAGE ALL OPEN POSITIONS ---
            for key in list(open_positions.keys()):
                # ... (rest of the trading logic is unchanged)
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

                logging.info(f"✅ Managing position {key}, z = {z:.3f}")

                entry_p1, entry_p2, qty1, qty2 = map(float, [pos['price1'], pos['price2'], pos['qty1'], pos['qty2']])
                pnl1 = (price1 - entry_p1) * qty1 if direction == 'BUY SPREAD' else (entry_p1 - price1) * qty1
                pnl2 = (entry_p2 - price2) * qty2 if direction == 'BUY SPREAD' else (price2 - entry_p2) * qty2
                current_pnl = pnl1 + pnl2
                entry_value = (entry_p1 * qty1) + (entry_p2 * qty2)
                pnl_pct = current_pnl / entry_value if entry_value != 0 else 0
                logging.info(f"Position PnL: {current_pnl:.4f} USD ({pnl_pct:+.2%})")

                exit_condition, reason = False, ""
                z_exit, stop_loss, take_profit = map(float,
                                                     [pair_config['z_exit'], pos['stop_loss'], pos['take_profit']])

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
                    logging.info(f"🔍 Checking pair {key}, z = {z:.3f}")
                    if abs(z) > float(pair['z_entry']):
                        direction = 'SELL SPREAD' if z > 0 else 'BUY SPREAD'
                        logging.info(f"Entry signal for {key}. Direction: {direction}.")
                        qty1, qty2 = TRADE_CAPITAL_PER_PAIR / price1, TRADE_CAPITAL_PER_PAIR / price2
                        if direction == 'SELL SPREAD':
                            if not (borrow_asset(sym1, qty1, isolated=USE_ISOLATED_MARGIN)): continue
                            if not (res1 := place_order(sym1, "SELL", qty1, isolated=USE_ISOLATED_MARGIN)): repay_asset(
                                sym1, qty1, isolated=USE_ISOLATED_MARGIN); continue
                            if not (res2 := place_order(sym2, "BUY", qty2, isolated=USE_ISOLATED_MARGIN)): place_order(
                                sym1, "BUY", qty1, isolated=USE_ISOLATED_MARGIN); repay_asset(sym1, qty1,
                                                                                              isolated=USE_ISOLATED_MARGIN); continue
                        else:
                            if not (borrow_asset(sym2, qty2, isolated=USE_ISOLATED_MARGIN)): continue
                            if not (res1 := place_order(sym1, "BUY", qty1, isolated=USE_ISOLATED_MARGIN)): repay_asset(
                                sym2, qty2, isolated=USE_ISOLATED_MARGIN); continue
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

        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            send_telegram_message(f"🚨 An unexpected error occurred: {e}. The bot is still running.")

        time.sleep(UPDATE_INTERVAL)

    logging.info("Bot has been shut down.")
    send_telegram_message("😴 *Bot has been shut down.*")


if __name__ == "__main__":
    run_bot()