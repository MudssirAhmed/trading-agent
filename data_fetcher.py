import ccxt
import pandas as pd
import ta
from bot_logger import log_info


def fetch_dataframe(exchange, symbol, timeframe, limit):
    """Helper to fetch OHLCV data and return a Pandas DataFrame."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def get_swing_levels(df, lookback=20):
    """
    Detect the most recent swing high and swing low from the last `lookback` candles.
    A swing high is a local max (higher than neighbours), swing low is a local min.
    Returns (swing_high, swing_low) as rounded floats.
    """
    window = df['close'].iloc[-lookback:]
    swing_high = round(window.max(), 2)
    swing_low = round(window.min(), 2)
    return swing_high, swing_low


def get_volume_ratio(df, window=20):
    """
    Computes the ratio of the latest candle's volume vs the rolling 20-period average.
    >1.5 = volume surge (breakout confirmation).
    <0.7 = low participation (avoid entries).
    """
    avg_vol = df['volume'].iloc[-window - 1:-1].mean()
    latest_vol = df['volume'].iloc[-2]
    if avg_vol == 0:
        return 1.0
    return round(latest_vol / avg_vol, 2)


def get_multi_timeframe_state(symbol="BTC/USDT"):
    """
    Fetches 1D, 1H, 5m, and 1m data, applies a rich set of indicators, and
    synthesizes a structured market state dict for the AI brain.

    Indicators added vs. original:
    - ATR (14) on all timeframes → correct SL/TP sizing
    - ADX (14) on 1D           → trend strength gate (trade only when ADX > 25)
    - MACD histogram on 1H     → divergence / momentum, not just a binary string
    - Volume ratio on 1H & 5m  → confirm breakouts, filter low-vol fakeouts
    - Swing high/low on 5m     → nearest S/R levels for entry context
    - RSI on 1H                → mid-timeframe momentum alignment
    """
    exchange = ccxt.binance()
    log_info(f"[DATA] Fetching enriched multi-timeframe data for {symbol}...", send_tg=False)

    # ── 1. MACRO: 1D Chart (Trend Identification + Strength) ─────────────────
    df_1d = fetch_dataframe(exchange, symbol, '1d', limit=250)
    df_1d['EMA_200'] = ta.trend.ema_indicator(df_1d['close'], window=200)
    df_1d['EMA_50']  = ta.trend.ema_indicator(df_1d['close'], window=50)
    df_1d['ATR']     = ta.volatility.average_true_range(df_1d['high'], df_1d['low'], df_1d['close'], window=14)
    df_1d['ADX']     = ta.trend.adx(df_1d['high'], df_1d['low'], df_1d['close'], window=14)
    latest_1d = df_1d.iloc[-2]   # use -2 to avoid incomplete forming candle

    macro_trend     = "Bullish" if latest_1d['close'] > latest_1d['EMA_200'] else "Bearish"
    ema_50_vs_200   = "Golden Cross" if latest_1d['EMA_50'] > latest_1d['EMA_200'] else "Death Cross"
    adx_value       = round(latest_1d['ADX'], 2)
    trend_strength  = "Strong" if adx_value > 25 else ("Weak" if adx_value > 15 else "No Trend")
    atr_1d          = round(latest_1d['ATR'], 2)

    # ── 2. MID: 1H Chart (Momentum + MACD Histogram) ─────────────────────────
    df_1h = fetch_dataframe(exchange, symbol, '1h', limit=150)
    df_1h['MACD']       = ta.trend.macd(df_1h['close'])
    df_1h['MACD_Signal']= ta.trend.macd_signal(df_1h['close'])
    df_1h['MACD_Hist']  = ta.trend.macd_diff(df_1h['close'])   # histogram
    df_1h['RSI']        = ta.momentum.rsi(df_1h['close'], window=14)
    df_1h['ATR']        = ta.volatility.average_true_range(df_1h['high'], df_1h['low'], df_1h['close'], window=14)
    latest_1h = df_1h.iloc[-2]
    prev_1h   = df_1h.iloc[-3]

    macd_cross       = "Bullish Cross" if latest_1h['MACD'] > latest_1h['MACD_Signal'] else "Bearish Cross"
    macd_hist        = round(latest_1h['MACD_Hist'], 4)
    macd_hist_prev   = round(prev_1h['MACD_Hist'], 4)
    macd_momentum    = "Accelerating" if abs(macd_hist) > abs(macd_hist_prev) else "Decelerating"
    rsi_1h           = round(latest_1h['RSI'], 2)
    atr_1h           = round(latest_1h['ATR'], 2)
    vol_ratio_1h     = get_volume_ratio(df_1h)

    # ── 3. MICRO: 5m Chart (Entry Triggers + S/R) ────────────────────────────
    df_5m = fetch_dataframe(exchange, symbol, '5m', limit=150)
    df_5m['RSI']    = ta.momentum.rsi(df_5m['close'], window=14)
    df_5m['BB_High']= ta.volatility.bollinger_hband(df_5m['close'])
    df_5m['BB_Mid'] = ta.volatility.bollinger_mavg(df_5m['close'])
    df_5m['BB_Low'] = ta.volatility.bollinger_lband(df_5m['close'])
    df_5m['ATR']    = ta.volatility.average_true_range(df_5m['high'], df_5m['low'], df_5m['close'], window=14)
    latest_5m = df_5m.iloc[-2]
    prev_5m   = df_5m.iloc[-3]

    # RSI divergence signal: price made higher high but RSI made lower high (bearish div)
    rsi_5m          = round(latest_5m['RSI'], 2)
    rsi_5m_prev     = round(prev_5m['RSI'], 2)
    price_5m        = round(latest_5m['close'], 2)
    price_5m_prev   = round(prev_5m['close'], 2)
    bearish_div     = (price_5m > price_5m_prev) and (rsi_5m < rsi_5m_prev)
    bullish_div     = (price_5m < price_5m_prev) and (rsi_5m > rsi_5m_prev)
    rsi_divergence  = "Bearish Divergence" if bearish_div else ("Bullish Divergence" if bullish_div else "None")

    # BB position
    bb_position     = "Above Upper Band" if price_5m > latest_5m['BB_High'] else (
                      "Below Lower Band" if price_5m < latest_5m['BB_Low'] else "Inside Bands")
    atr_5m          = round(latest_5m['ATR'], 4)
    vol_ratio_5m    = get_volume_ratio(df_5m)
    swing_high_5m, swing_low_5m = get_swing_levels(df_5m, lookback=30)

    # ── 4. NANO: 1m Chart (Live Price) ───────────────────────────────────────
    df_1m = fetch_dataframe(exchange, symbol, '1m', limit=10)
    current_price = df_1m.iloc[-1]['close']

    # ── 5. Risk Sizing Guide (ATR-based) ─────────────────────────────────────
    # SL = 2× ATR (enough room beyond noise), TP = 5× ATR (2.5:1 RR minimum)
    # Using 1H ATR for SL/TP — more stable than 5m ATR which can be very small
    suggested_sl_distance = round(atr_1h * 2.0, 2)
    suggested_tp_distance = round(atr_1h * 5.0, 2)

    log_info(
        f"[DATA] Price=${current_price:,.2f} | Trend={macro_trend} ADX={adx_value} | "
        f"1H RSI={rsi_1h} | 5m RSI={rsi_5m} | VolRatio={vol_ratio_5m}x",
        send_tg=False
    )

    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),

        "macro_1D": {
            "trend": macro_trend,
            "ema_200": round(latest_1d['EMA_200'], 2),
            "ema_50": round(latest_1d['EMA_50'], 2),
            "ema_alignment": ema_50_vs_200,
            "adx": adx_value,
            "trend_strength": trend_strength,
            "atr": atr_1d,
        },

        "mid_1H": {
            "close": round(latest_1h['close'], 2),
            "rsi": rsi_1h,
            "macd_cross": macd_cross,
            "macd_histogram": macd_hist,
            "macd_momentum": macd_momentum,   # Accelerating / Decelerating
            "atr": atr_1h,
            "volume_ratio": vol_ratio_1h,     # vs 20-period avg
        },

        "micro_5m": {
            "close": price_5m,
            "rsi": rsi_5m,
            "rsi_divergence": rsi_divergence,
            "bb_high": round(latest_5m['BB_High'], 2),
            "bb_mid": round(latest_5m['BB_Mid'], 2),
            "bb_low": round(latest_5m['BB_Low'], 2),
            "bb_position": bb_position,
            "swing_high_30c": swing_high_5m,  # resistance context
            "swing_low_30c": swing_low_5m,    # support context
            "atr": atr_5m,
            "volume_ratio": vol_ratio_5m,
        },

        "risk_sizing": {
            "suggested_sl_distance": suggested_sl_distance,
            "suggested_tp_distance": suggested_tp_distance,
            "note": "Based on 1.5x and 3.0x ATR(14) on the 5m chart. Gives minimum 2:1 RR."
        }
    }