# AI Crypto Trading Agent

This project is a multi-timeframe algorithmic trading agent using a **Retrieval-Augmented Generation (RAG)** architecture and an **Experience Loop**.

The AI references a local vector database built from technical analysis books to make mathematically sound trading decisions, and maintains an Experience Database to learn from past trades through a Critic AI reflection loop.

## Architecture Overview

The system runs on a continuous **5-Minute Pipeline**:
1. **Multi-Timeframe Analysis (MTFA):** Fetches 1D, 1H, 5m, and 1m OHLCV data via `ccxt` (Binance) to establish macro trend and micro entry triggers.
2. **RAG Knowledge Base & Experience DB:** Queries a local ChromaDB containing embedded trading books for historical precedent, and checks past trade reflections to avoid repeating mistakes.
3. **AI Synthesizer:** An LLM (GPT-4o-mini) processes the technicals, theory, and past experience to propose a trade with calculated confidence, stop-loss, and take-profit.
4. **Execution & Monitoring:** The system logs trades to a local JSON file, tracks performance, and monitors for stop-loss/take-profit hits.
5. **Dashboard & Alerts:** A Streamlit dashboard tracks the equity curve and win rate, while a Telegram bot sends real-time entry and exit alerts.

## Setup Instructions

1. **Clone and create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install ccxt pandas ta langchain-chroma langchain-openai langchain-core langchain-community pypdf python-dotenv requests streamlit plotly watchdog "sqlalchemy[asyncio]"
   ```

3. **Environment Variables:**
   Create a `.env` file in the root directory:
   ```text
   OPENAI_API_KEY=your-openai-api-key
   TELEGRAM_BOT_TOKEN=your-telegram-bot-token
   TELEGRAM_CHAT_ID=your-telegram-chat-id
   ```

## Building the Knowledge Base

We use an **Incremental Indexing** script (`build_knowledge_base.py`) to process PDF books without duplicating data.

1. Create a directory named `trading_books` and drop your PDF books inside.
2. Run the ingestion script:
   ```bash
   python build_knowledge_base.py
   ```

## Running the Engine

You can start the entire suite (Trading Engine + Streamlit Dashboard) with the included shell script:

```bash
chmod +x run_all.sh
./run_all.sh
```

- The trading agent runs in the background.
- The interactive Streamlit dashboard is available at `http://localhost:8501`.
- To safely stop the bot and dashboard, press `Ctrl+C`.

## Database Management

To clear the RAG knowledge base, experience database, or trade history, use the built-in database manager:

```bash
python db_manager.py
```

## Deployment

For Ubuntu/Linux deployment, an `init.sh` script is provided which will install system dependencies, update the environment, and restart background services using `tmux`.