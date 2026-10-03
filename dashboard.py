import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json

# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Trading Agent Dashboard", layout="wide")
st.title("🤖 AI Trading Agent Performance")

# --- LIVE ONGOING TRADE STATUS ---
st.subheader("📡 Live Position Status")

if os.path.exists("active_trade.json"):
    try:
        with open("active_trade.json", "r") as f:
            trade_data = json.load(f)
            
        action = trade_data.get('action', 'TRADE')
        symbol = trade_data.get('context', {}).get('symbol', 'BTC/USDT')
        entry = trade_data.get('entry_price', 0)
        tp = trade_data.get('take_profit', 0)
        sl = trade_data.get('stop_loss', 0)

        # Highlight ongoing trade in a prominent alert card
        st.warning(f"🚨 **ACTIVE {action} POSITION:** {symbol}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Entry Price", f"${entry:,.2f}")
        c2.metric("Take Profit", f"${tp:,.2f}")
        c3.metric("Stop Loss", f"${sl:,.2f}")
    except Exception as e:
        st.info("No active trades currently open. Scanning markets...")
else:
    st.info("🟢 No active trades currently open. Market scanner is active...")

st.markdown("---")

# --- LOAD DATA ---
@st.cache_data(ttl=60) # Refreshes data every 60 seconds automatically
def load_data():
    if not os.path.exists('trade_history.csv'):
        return pd.DataFrame()
    df = pd.read_csv('trade_history.csv')
    df['Date'] = pd.to_datetime(df['Date'])
    df['Cumulative_PnL'] = df['PnL_USD'].cumsum()
    return df

df = load_data()

if df.empty:
    st.warning("No closed trades recorded yet. Performance charts and historical logs will populate once the bot closes its first trade.")
else:
    # --- TOP METRICS ---
    total_trades = len(df)
    wins = len(df[df['Outcome'] == 'WIN'])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    total_profit = df['PnL_USD'].sum()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", total_trades)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Total PnL (Based on $10k pos)", f"${total_profit:,.2f}")
    col4.metric("Active Pairs", df['Symbol'].nunique())
    
    st.markdown("---")
    
    # --- CHARTS ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Equity Curve (Cumulative PnL)")
        # Interactive Plotly Line Chart
        fig_equity = px.line(df, x='Date', y='Cumulative_PnL', markers=True, 
                             title="Profit Growth Over Time",
                             color_discrete_sequence=["#00ff00" if total_profit >= 0 else "#ff0000"])
        st.plotly_chart(fig_equity, use_container_width=True)
        
    with col2:
        st.subheader("Win / Loss Ratio")
        # Interactive Plotly Pie Chart
        fig_pie = px.pie(df, names='Outcome', title="Trade Outcomes",
                         color='Outcome', color_discrete_map={'WIN': '#00b050', 'LOSS': '#ff0000'})
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")
    
    # --- FILTERABLE DATA TABLE ---
    st.subheader("Trade History Log")
    
    # Custom Filters
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        action_filter = st.multiselect("Filter by Action:", options=df['Action'].unique(), default=df['Action'].unique())
    with filter_col2:
        outcome_filter = st.multiselect("Filter by Outcome:", options=df['Outcome'].unique(), default=df['Outcome'].unique())
    
    # Apply filters
    filtered_df = df[(df['Action'].isin(action_filter)) & (df['Outcome'].isin(outcome_filter))]
    
    # Render the interactive dataframe
    st.dataframe(
        filtered_df[['Date', 'Symbol', 'Action', 'Entry_Price', 'Exit_Price', 'Outcome', 'PnL_USD']].sort_values(by="Date", ascending=False),
        use_container_width=True,
        hide_index=True
    )

st.markdown("---")
st.subheader("🖥️ System Logs (Real-time)")
if os.path.exists('engine.log'):
    with open('engine.log', 'r') as log_file:
        # Get the last 50 lines
        lines = log_file.readlines()[-50:]
        log_content = "".join(lines)
        st.text_area("Latest engine.log", log_content, height=300, disabled=True)
else:
    st.info("No system logs generated yet.")