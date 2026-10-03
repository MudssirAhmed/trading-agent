#!/bin/bash

# Always run from the directory where this script lives.
# Critical when launched from tmux — tmux starts in home dir, not project root.
cd "$(dirname "$0")"

echo "🚀 Starting AI Trading Suite..."

# 1. Activate the virtual environment
source venv/bin/activate

# 2. Start the main trading bot in the background
echo "🤖 Starting Trading Agent (main.py)..."
python main.py &
BOT_PID=$!

# 3. Start the Streamlit dashboard in headless background mode
echo "📊 Starting Dashboard (dashboard.py)..."
python -m streamlit run dashboard.py --server.headless true --server.address 0.0.0.0 --server.port 8501 &
DASHBOARD_PID=$!

# 4. Catch shutdown signals to safely kill both background processes
trap "echo -e '\n🛑 Shutting down Trading Agent and Dashboard...'; kill $BOT_PID $DASHBOARD_PID; exit" SIGINT SIGTERM

echo "✅ Both applications are running!"
echo "👉 Dashboard is live on Port 8501"
echo "Press Ctrl+C at any time to stop everything."

# Keep the script alive until a signal is received
wait