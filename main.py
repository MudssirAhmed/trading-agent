import time
import os
import csv
import json
from datetime import datetime
from dotenv import load_dotenv
from data_fetcher import get_multi_timeframe_state
from memory_manager import get_textbook_theory, get_past_experience, save_lesson_to_memory
from ai_brain import generate_trade_decision, generate_reflection
from notifier import send_telegram_alert

load_dotenv()

active_trade = None
TRADE_FILE = "active_trade.json"

def save_active_trade(trade_data):
    """Saves the active trade to disk for reboot recovery and dashboard viewing."""
    with open(TRADE_FILE, "w") as f:
        json.dump(trade_data, f)

def clear_active_trade():
    """Removes the active trade file when a trade closes."""
    if os.path.exists(TRADE_FILE):
        os.remove(TRADE_FILE)

def log_trade_to_csv(trade_context, final_price, outcome_type):
    """Logs the math of a closed trade to a CSV file for the dashboard."""
    file_exists = os.path.isfile('trade_history.csv')
    
    # Calculate Profit/Loss assuming a standard $1,000 position size for the chart
    entry = trade_context['decision']['entry_price']
    action = trade_context['decision']['action']
    
    if action == "LONG":
        pnl_percent = (final_price - entry) / entry
    else:
        pnl_percent = (entry - final_price) / entry
        
    estimated_pnl_dollars = 1000 * pnl_percent
    
    with open('trade_history.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        # Write headers if the file is new
        if not file_exists:
            writer.writerow(['Date', 'Symbol', 'Action', 'Entry_Price', 'Exit_Price', 'Outcome', 'PnL_USD'])
            
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            trade_context['symbol'],
            action,
            round(entry, 2),
            round(final_price, 2),
            outcome_type,
            round(estimated_pnl_dollars, 2)
        ])

def monitor_trade(current_price):
    """Monitors open position and triggers reflection and alert if SL/TP is hit."""
    global active_trade
    if not active_trade:
        return False
        
    print(f"[TRACKER] Open {active_trade['action']} | Price: ${current_price:,.2f} | SL: ${active_trade['stop_loss']:,.2f} | TP: ${active_trade['take_profit']:,.2f}")
    
    outcome = None
    if active_trade['action'] == "LONG":
        if current_price <= active_trade['stop_loss']:
            outcome = f"LOSS. Stopped out at ${current_price:,.2f}."
        elif current_price >= active_trade['take_profit']:
            outcome = f"WIN. Take profit hit at ${current_price:,.2f}."
            
    elif active_trade['action'] == "SHORT":
        if current_price >= active_trade['stop_loss']:
            outcome = f"LOSS. Stopped out at ${current_price:,.2f}."
        elif current_price <= active_trade['take_profit']:
            outcome = f"WIN. Take profit hit at ${current_price:,.2f}."

    if outcome:
        print(f"\n[ALERT] Trade Closed! {outcome}")
        
        # Determine if it was a WIN or LOSS for the dashboard
        outcome_type = "WIN" if "WIN" in outcome else "LOSS"

        # Log to the CSV dashboard file
        log_trade_to_csv(active_trade['context'], current_price, outcome_type)

        # 1. Critic AI evaluates the trade
        lesson = generate_reflection(active_trade['context'], outcome)
        print(f"[CRITIC] {lesson}")
        
        # 2. Save lesson to Experience DB
        save_lesson_to_memory(lesson, active_trade['context']['symbol'])
        
        # 3. Notify via Telegram
        alert_body = (
            f"🔔 <b>TRADE CLOSED: {active_trade['action']}</b>\n"
            f"<b>Result:</b> {outcome}\n\n"
            f"<b>Critic Reflection:</b>\n{lesson}"
        )
        send_telegram_alert(alert_body)
        
        # 4. Clear trade state from memory and disk
        active_trade = None
        clear_active_trade()
        return True
        
    return False

def bot_loop():
    global active_trade
    print("\n" + "="*40)
    
    # 1. Ingest Data
    state = get_multi_timeframe_state("BTC/USDT")
    current_price = state['current_price']
    
    # 2. Check Open Trades
    if active_trade:
        monitor_trade(current_price)
        return
        
    # 3. Translate Math to Semantic Search Query
    search_query = f"1D {state['macro_1D']['trend']}, 1H MACD {state['mid_1H']['macd']}, 5m RSI {state['micro_5m']['rsi']}"
    
    # 4. Retrieve Knowledge
    theory = get_textbook_theory(search_query)
    experience = get_past_experience(search_query)
    
    # 5. Synthesize Decision
    print("[BRAIN] Synthesizing MTFA data...")
    decision = generate_trade_decision(state, theory, experience)
    
    if decision:
        print(f"\n[DECISION] {decision['action']} (Confidence: {decision['confidence']}%)")
        print(f"[REASONING] {decision['reasoning']}")
        
       # 6. Execute Alert
        if decision['action'] != "HOLD" and decision['confidence'] >= 85:
            print(f"\n🚀 EXECUTING {decision['action']} ENTRY AT ${decision['entry_price']}")
            
            trade_msg = (
                f"🚨 <b>AI TRADE SIGNAL: {decision['action']} BTC</b> 🚨\n\n"
                f"<b>Confidence:</b> {decision['confidence']}%\n"
                f"<b>Entry:</b> ${decision['entry_price']:,.2f}\n"
                f"<b>Stop Loss:</b> ${decision['stop_loss']:,.2f}\n"
                f"<b>Take Profit:</b> ${decision['take_profit']:,.2f}\n\n"
                f"<b>Macro Trend (1D):</b> {state['macro_1D']['trend']}\n"
                f"<b>1H MACD:</b> {state['mid_1H']['macd']}\n"
                f"<b>5m RSI:</b> {state['micro_5m']['rsi']}\n\n"
                f"<b>Strategy Reasoning:</b>\n{decision['reasoning']}"
            )
            send_telegram_alert(trade_msg)
            
            active_trade = {
                "action": decision['action'],
                "entry_price": decision['entry_price'],
                "stop_loss": decision['stop_loss'],
                "take_profit": decision['take_profit'],
                "context": {"symbol": state['symbol'], "state": state, "decision": decision}
            }
            
            # Save trade state to disk immediately
            save_active_trade(active_trade)

def startup_check():
    """Checks for existing trades on boot and notifies Telegram."""
    global active_trade
    if os.path.exists(TRADE_FILE):
        try:
            with open(TRADE_FILE, "r") as f:
                active_trade = json.load(f)
            
            recovery_msg = (
                f"🔄 <b>System Restarted</b>\n"
                f"Recovered ongoing <b>{active_trade['action']}</b> trade for "
                f"<b>{active_trade['context']['symbol']}</b> at <b>${active_trade['entry_price']:,.2f}</b>. "
                f"Resuming monitoring..."
            )
            send_telegram_alert(recovery_msg)
            print("⚠️ Recovered an ongoing trade from disk!")
        except Exception as e:
            print(f"Failed to load active trade: {e}")
            active_trade = None
            send_telegram_alert("🤖 <b>AI Trading Engine Initialized.</b> Running multi-timeframe analysis every 5 minutes...")
    else:
        send_telegram_alert("🤖 <b>AI Trading Engine Initialized.</b> Running multi-timeframe analysis every 5 minutes...")

if __name__ == "__main__":
    startup_check()
    
    while True:
        try:
            bot_loop()
            time.sleep(300)
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(60)