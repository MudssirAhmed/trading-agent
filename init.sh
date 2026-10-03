#!/bin/bash

set -e

cd "$(dirname "$0")"

echo "=================================================="
echo "🚀 Initializing and Deploying AI Trading Engine"
echo "=================================================="

# Install system dependencies required by the application.
echo -e "\n[1/6] Updating Ubuntu packages and installing core tools..."
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip python3-dev build-essential unzip tmux sqlite3 curl

# Preserve local databases and configuration across the source reset.
echo -e "\n[2/6] Safeguarding local databases and environment config..."
backup_dir=$(mktemp -d /tmp/bot_backup.XXXXXX)
if [ -d "chroma_db" ]; then cp -a chroma_db "$backup_dir/"; fi
if [ -d "experience_db" ]; then cp -a experience_db "$backup_dir/"; fi
if [ -f "trade_history.csv" ]; then cp trade_history.csv "$backup_dir/"; fi
if [ -f ".env" ]; then cp .env "$backup_dir/"; fi
if [ -f "active_trade.json" ]; then cp active_trade.json "$backup_dir/"; fi

keep_backup_on_failure() {
    if [ -d "$backup_dir" ]; then
        echo "Local data backup retained at: $backup_dir"
    fi
}
trap keep_backup_on_failure EXIT

# This intentionally replaces tracked local code with the latest main branch.
echo -e "\n[3/6] Pulling latest updates from GitHub..."
git fetch origin
git reset --hard origin/main

echo -e "\n[4/6] Restoring databases and environment config..."
if [ -d "$backup_dir/chroma_db" ]; then cp -a "$backup_dir/chroma_db" ./; fi
if [ -d "$backup_dir/experience_db" ]; then cp -a "$backup_dir/experience_db" ./; fi
if [ -f "$backup_dir/trade_history.csv" ]; then cp "$backup_dir/trade_history.csv" ./; fi
if [ -f "$backup_dir/.env" ]; then cp "$backup_dir/.env" ./; fi
if [ -f "$backup_dir/active_trade.json" ]; then cp "$backup_dir/active_trade.json" ./; fi
rm -rf "$backup_dir"
trap - EXIT

echo -e "\n[5/6] Updating Python environment and packages..."
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

chmod +x run_all.sh

echo -e "\n[6/6] Restarting background bot services..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/bot_startup.log"

# Kill any existing session
tmux kill-session -t bot 2>/dev/null || true

# Launch in tmux — redirect all output to a startup log so crashes are visible
# '|| true' prevents set -e from killing this script if tmux exits immediately
tmux new-session -d -s bot "bash $SCRIPT_DIR/run_all.sh > $LOG_FILE 2>&1" || true

# Give the session 3 seconds to either stabilise or crash
sleep 3

# Check if session is actually alive
if tmux has-session -t bot 2>/dev/null; then
    echo "=================================================="
    echo "✅ Setup and deployment complete."
    echo "=================================================="
    echo "Bot is running. To view live logs:"
    echo "  tmux attach -t bot"
    echo "  tail -f $LOG_FILE"
else
    echo "=================================================="
    echo "❌ Bot session crashed on startup. Last log output:"
    echo "=================================================="
    cat "$LOG_FILE" 2>/dev/null || echo "(no log output captured)"
    echo ""
    echo "Fix the error above, then re-run: ./init.sh"
    exit 1
fi