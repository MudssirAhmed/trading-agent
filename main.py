import time
import os
import csv
import json
import traceback
from datetime import datetime
from dotenv import load_dotenv

from data_fetcher import get_multi_timeframe_state
from memory_manager import get_textbook_theory, get_past_experience, save_lesson_to_memory
from ai_brain import generate_trade_decision, generate_reflection
from notifier import send_telegram_alert
from bot_logger import log_info, log_error, log_warning

load_dotenv()

active_trade = None
TRADE_FILE   = "active_trade.json"

# ── Persistence ───────────────────────────────────────────────────────────────

def save_active_trade(trade_data):
    """Saves the active trade to disk for reboot recovery and dashboard viewing."""
    with open(TRADE_FILE, "w") as f:
        json.dump(trade_data, f, indent=2)

def clear_active_trade():
    """Removes the active trade file when a trade closes."""
    if os.path.exists(TRADE_FILE):
        os.remove(TRADE_FILE)

def log_trade_to_csv(trade_context, final_price, outcome_type):
    """Logs the math of a closed trade to a CSV file for the dashboard."""
    file_exists = os.path.isfile('trade_history.csv')

    entry  = trade_context['decision']['entry_price']
    action = trade_context['decision']['action']
    rr     = trade_context['decision'].get('risk_reward_ratio', 0)

    if action == "LONG":
        pnl_percent = (final_price - entry) / entry
    else:
        pnl_percent = (entry - final_price) / entry

    estimated_pnl_dollars = 10_000 * pnl_percent

    with open('trade_history.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                'Date', 'Symbol', 'Action', 'Entry_Price', 'Exit_Price',
                'Outcome', 'PnL_USD', 'RR_Ratio', 'Confidence'
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            trade_context['symbol'],
            action,
            round(entry, 2),
            round(final_price, 2),
            outcome_type,
            round(estimated_pnl_dollars, 2),
            rr,
            trade_context['decision'].get('confidence', 0)
        ])

# ── Trade Monitoring ──────────────────────────────────────────────────────────

def _close_trade(current_price: float, outcome_label: str, outcome_type: str):
    """Handles the full close sequence: log, reflect, save lesson, alert."""
    global active_trade

    log_info(f"[ALERT] Trade Closed! {outcome_label}", send_tg=True)
    log_trade_to_csv(active_trade['context'], current_price, outcome_type)

    # Generate structured reflection
    reflection = generate_reflection(active_trade['context'], outcome_label)
    log_info(f"[CRITIC] {reflection}", send_tg=True)

    # Build regime string for experience DB metadata
    state    = active_trade['context'].get('state', {})
    macro    = state.get('macro_1D', {})
    regime   = (
        f"{macro.get('trend', '?')} {macro.get('trend_strength', '?')} "
        f"ADX={macro.get('adx', '?')}"
    )

    # Save lesson with quality gates and rich metadata
    save_lesson_to_memory(
        lesson_text=reflection,
        symbol=active_trade['context']['symbol'],
        outcome=outcome_type,
        confidence=active_trade['context']['decision'].get('confidence', 0),
        regime=regime
    )

    alert_body = (
        f"🔔 <b>TRADE CLOSED: {active_trade['action']}</b>\n"
        f"<b>Result:</b> {outcome_label}\n\n"
        f"<b>Critic Reflection:</b>\n{reflection}"
    )
    send_telegram_alert(alert_body)

    active_trade = None
    clear_active_trade()


def monitor_trade(state: dict) -> bool:
    """
    Monitors the open position with:
    1. SL/TP hit detection
    2. Trend invalidation alert (1D trend flips against trade direction)
    3. ATR-based trailing stop update

    Returns True if trade was closed, False if still open.
    """
    global active_trade
    if not active_trade:
        return False

    current_price = state['current_price']
    action        = active_trade['action']
    sl            = active_trade['stop_loss']
    tp            = active_trade['take_profit']
    entry         = active_trade['entry_price']

    log_info(
        f"[TRACKER] Open {action} | Price: ${current_price:,.2f} | "
        f"SL: ${sl:,.2f} | TP: ${tp:,.2f} | "
        f"PnL: {((current_price - entry) / entry * 100 if action == 'LONG' else (entry - current_price) / entry * 100):.2f}%",
        send_tg=False
    )

    # ── 1. SL / TP Hit ────────────────────────────────────────────────────────
    outcome_label = None
    outcome_type  = None

    if action == "LONG":
        if current_price <= sl:
            outcome_label = f"LOSS. Stopped out at ${current_price:,.2f}."
            outcome_type  = "LOSS"
        elif current_price >= tp:
            outcome_label = f"WIN. Take profit hit at ${current_price:,.2f}."
            outcome_type  = "WIN"
    elif action == "SHORT":
        if current_price >= sl:
            outcome_label = f"LOSS. Stopped out at ${current_price:,.2f}."
            outcome_type  = "LOSS"
        elif current_price <= tp:
            outcome_label = f"WIN. Take profit hit at ${current_price:,.2f}."
            outcome_type  = "WIN"

    if outcome_label:
        _close_trade(current_price, outcome_label, outcome_type)
        return True

    # ── 2. Trend Invalidation Alert ───────────────────────────────────────────
    live_trend = state['macro_1D']['trend']
    if action == "LONG" and live_trend == "Bearish":
        warning = (
            f"⚠️ <b>TRADE INVALIDATION WARNING</b>\n"
            f"Open LONG but 1D trend has flipped to <b>Bearish</b>.\n"
            f"Current Price: ${current_price:,.2f} | Entry: ${entry:,.2f}\n"
            f"Consider manual exit to protect capital."
        )
        log_warning("[MONITOR] 1D trend flipped Bearish on open LONG!", send_tg=True)
        send_telegram_alert(warning)

    elif action == "SHORT" and live_trend == "Bullish":
        warning = (
            f"⚠️ <b>TRADE INVALIDATION WARNING</b>\n"
            f"Open SHORT but 1D trend has flipped to <b>Bullish</b>.\n"
            f"Current Price: ${current_price:,.2f} | Entry: ${entry:,.2f}\n"
            f"Consider manual exit to protect capital."
        )
        log_warning("[MONITOR] 1D trend flipped Bullish on open SHORT!", send_tg=True)
        send_telegram_alert(warning)

    # ── 3. ATR Trailing Stop ──────────────────────────────────────────────────
    atr_at_entry = active_trade.get('atr_at_entry')
    if atr_at_entry:
        trail_distance = atr_at_entry * 2.0   # 2× ATR trailing distance

        if action == "LONG":
            new_sl = round(current_price - trail_distance, 2)
            if new_sl > active_trade['stop_loss']:
                log_info(
                    f"[TRAIL] LONG trailing stop moved up: ${active_trade['stop_loss']:,.2f} → ${new_sl:,.2f}",
                    send_tg=False
                )
                active_trade['stop_loss'] = new_sl
                save_active_trade(active_trade)

        elif action == "SHORT":
            new_sl = round(current_price + trail_distance, 2)
            if new_sl < active_trade['stop_loss']:
                log_info(
                    f"[TRAIL] SHORT trailing stop moved down: ${active_trade['stop_loss']:,.2f} → ${new_sl:,.2f}",
                    send_tg=False
                )
                active_trade['stop_loss'] = new_sl
                save_active_trade(active_trade)

    return False


# ── Main Bot Loop ─────────────────────────────────────────────────────────────

def bot_loop():
    global active_trade
    log_info("="*50, send_tg=False)

    # Always fetch fresh market data (needed for monitoring AND new trade analysis)
    try:
        state = get_multi_timeframe_state("BTC/USDT")
        current_price = state['current_price']
    except Exception as e:
        log_error(f"Failed to fetch market data: {e}", send_tg=True)
        return

    # ── If trade is open: monitor it (+ check invalidation + trail stop) ──────
    if active_trade:
        trade_closed = monitor_trade(state)
        if not trade_closed:
            # Log a brief status — don't look for new trades while one is active
            log_info(
                f"[STATUS] Trade open. Monitoring. Next analysis check in 5min.",
                send_tg=False
            )
        return

    # ── No active trade: run full analysis pipeline ───────────────────────────
    log_info("[BRAIN] No active trade. Running MTFA pipeline...", send_tg=False)

    try:
        # Pass the full state dict (not a raw string) so memory manager can
        # build semantic queries per signal dimension
        theory     = get_textbook_theory(state)
        experience = get_past_experience(state)
    except Exception as e:
        log_error(f"Failed to retrieve from ChromaDB: {e}", send_tg=True)
        return

    log_info("[BRAIN] Synthesizing MTFA data with two-stage AI pipeline...", send_tg=False)
    decision = generate_trade_decision(state, theory, experience)

    if not decision:
        log_error("Failed to generate trade decision (AI error)", send_tg=True)
        return

    action     = decision.get('action', 'HOLD')
    confidence = decision.get('confidence', 0)
    rr         = decision.get('risk_reward_ratio', 0)

    log_info(
        f"[DECISION] {action} | Confidence: {confidence}% | RR: {rr:.2f}",
        send_tg=True
    )
    log_info(f"[THEORY]   {decision.get('theory_cited', 'None')}", send_tg=False)
    log_info(f"[LESSON]   {decision.get('experience_cited', 'None')}", send_tg=False)
    log_info(f"[REASON]   {decision.get('reasoning', '')}", send_tg=False)

    # Execution gate: must be a directional trade, >=85% confidence, RR >= 2
    if action != "HOLD" and confidence >= 85 and rr >= 2.0:
        log_info(f"🚀 EXECUTING {action} ENTRY AT ${decision['entry_price']}", send_tg=True)

        trade_msg = (
            f"🚨 <b>AI TRADE SIGNAL: {action} BTC</b> 🚨\n\n"
            f"<b>Confidence:</b> {confidence}%\n"
            f"<b>Risk:Reward:</b> 1:{rr}\n"
            f"<b>Entry:</b> ${decision['entry_price']:,.2f}\n"
            f"<b>Stop Loss:</b> ${decision['stop_loss']:,.2f}\n"
            f"<b>Take Profit:</b> ${decision['take_profit']:,.2f}\n\n"
            f"<b>Macro Trend (1D):</b> {state['macro_1D']['trend']} | "
            f"ADX: {state['macro_1D']['adx']} ({state['macro_1D']['trend_strength']})\n"
            f"<b>1H MACD:</b> {state['mid_1H']['macd_cross']} | Histogram: {state['mid_1H']['macd_histogram']}\n"
            f"<b>5m RSI:</b> {state['micro_5m']['rsi']} | BB: {state['micro_5m']['bb_position']}\n"
            f"<b>Volume Ratio:</b> {state['micro_5m']['volume_ratio']}×\n\n"
            f"<b>Book Reference:</b> {decision.get('theory_cited', 'None')}\n"
            f"<b>Past Lesson:</b> {decision.get('experience_cited', 'None')}\n\n"
            f"<b>Strategy Reasoning:</b>\n{decision['reasoning']}"
        )
        send_telegram_alert(trade_msg)

        # Store ATR at entry for trailing stop calculations
        atr_at_entry = state['micro_5m'].get('atr', None)

        active_trade = {
            "action":       action,
            "entry_price":  decision['entry_price'],
            "stop_loss":    decision['stop_loss'],
            "take_profit":  decision['take_profit'],
            "atr_at_entry": atr_at_entry,
            "context": {
                "symbol":   state['symbol'],
                "state":    state,
                "decision": decision
            }
        }
        save_active_trade(active_trade)

    elif action != "HOLD":
        log_info(
            f"[GATE] Signal not executed — Confidence: {confidence}% (need ≥85%) | "
            f"RR: {rr:.2f} (need ≥2.0)",
            send_tg=False
        )


# ── Startup ───────────────────────────────────────────────────────────────────

def startup_check():
    global active_trade
    if os.path.exists(TRADE_FILE):
        try:
            with open(TRADE_FILE, "r") as f:
                active_trade = json.load(f)
            recovery_msg = (
                f"🔄 <b>System Restarted</b>\n"
                f"Recovered ongoing <b>{active_trade['action']}</b> trade for "
                f"<b>{active_trade['context']['symbol']}</b> at "
                f"<b>${active_trade['entry_price']:,.2f}</b>. Resuming monitoring..."
            )
            send_telegram_alert(recovery_msg)
            log_warning("Recovered an ongoing trade from disk!", send_tg=True)
        except Exception as e:
            log_error(f"Failed to load active trade: {e}", send_tg=True)
            active_trade = None
            send_telegram_alert(
                "🤖 <b>AI Trading Engine Initialized.</b> Running enriched MTFA every 5 minutes..."
            )
    else:
        send_telegram_alert(
            "🤖 <b>AI Trading Engine Initialized.</b> Running enriched MTFA every 5 minutes..."
        )
        log_info("AI Trading Engine Initialized.", send_tg=True)


if __name__ == "__main__":
    startup_check()

    while True:
        try:
            bot_loop()
            time.sleep(300)  # 5-minute cycle
        except Exception as e:
            log_error(f"Error in main loop: {e}\n{traceback.format_exc()}", send_tg=True)
            time.sleep(60)