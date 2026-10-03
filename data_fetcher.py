import ccxt
import pandas as pd
import ta
import time
from bot_logger import log_info

def fetch_dataframe(exchange, symbol, timeframe, limit):
    """Helper to fetch data and return a Pandas DataFrame."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_multi_timeframe_state(symbol="BTC/USDT"):
    """Fetches 1D, 1H, 5m, and 1m data, applies indicators, and synthesizes a market state."""
    exchange = ccxt.binance()
    log_info(f"[DATA] Fetching multi-timeframe data for {symbol}...", send_tg=False)
    
    # 1. Macro: 1D Chart (Trend Identification)
    df_1d = fetch_dataframe(exchange, symbol, '1d', limit=250)
    df_1d['EMA_200'] = ta.trend.ema_indicator(df_1d['close'], window=200)
    latest_1d = df_1d.iloc[-2]
    macro_trend = "Bullish" if latest_1d['close'] > latest_1d['EMA_200'] else "Bearish"

    # 2. Mid: 1H Chart (Momentum & MACD)
    df_1h = fetch_dataframe(exchange, symbol, '1h', limit=100)
    df_1h['MACD'] = ta.trend.macd(df_1h['close'])
    df_1h['MACD_Signal'] = ta.trend.macd_signal(df_1h['close'])
    latest_1h = df_1h.iloc[-2]
    macd_state = "Bullish Cross" if latest_1h['MACD'] > latest_1h['MACD_Signal'] else "Bearish Cross"

    # 3. Micro: 5m Chart (Triggers & Volatility)
    df_5m = fetch_dataframe(exchange, symbol, '5m', limit=100)
    df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], window=14)
    df_5m['BB_High'] = ta.volatility.bollinger_hband(df_5m['close'])
    df_5m['BB_Low'] = ta.volatility.bollinger_lband(df_5m['close'])
    latest_5m = df_5m.iloc[-2]
    
    # 4. Nano: 1m Chart (Immediate Price Action)
    df_1m = fetch_dataframe(exchange, symbol, '1m', limit=10)
    latest_1m = df_1m.iloc[-1] # We take the live forming candle here for exact entry

    # Compile the state
    return {
        "symbol": symbol,
        "current_price": latest_1m['close'],
        "macro_1D": {
            "trend": macro_trend,
            "ema_200": round(latest_1d['EMA_200'], 2)
        },
        "mid_1H": {
            "macd": macd_state,
            "close": latest_1h['close']
        },
        "micro_5m": {
            "rsi": round(latest_5m['RSI'], 2),
            "bb_high": round(latest_5m['BB_High'], 2),
            "bb_low": round(latest_5m['BB_Low'], 2),
            "volume": latest_5m['volume']
        }
    }