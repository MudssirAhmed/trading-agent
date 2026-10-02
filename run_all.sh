#!/bin/bash

echo "🚀 Starting AI Trading Suite..."

# 1. Activate the virtual environment
source venv/bin/activate

# 2. Start the main trading bot in the background
echo "🤖 Starting Trading Agent (main.py)..."
python main.py &
BOT_PID=$!

# 3. Start the Streamlit dashboard in the background
echo "📊 Starting Dashboard (dashboard.py)..."
streamlit run dashboard.py &
DASHBOARD_PID=$!

# 4. Catch the Ctrl+C command to safely kill both background processes
trap "echo -e '\n🛑 Shutting down Trading Agent and Dashboard...'; kill $BOT_PID $DASHBOARD_PID; exit" SIGINT SIGTERM

echo "✅ Both applications are running!"
echo "👉 Dashboard is live at: http://localhost:8501"
echo "Press Ctrl+C at any time to stop everything."

# Keep the script running and wait for user interruption
wait