# AI Crypto Trading Agent (RAG-Powered)

This project is a sophisticated, multi-timeframe algorithmic trading agent. Rather than relying on simple technical indicators or hallucination-prone AI prompts, it uses a **Retrieval-Augmented Generation (RAG)** architecture. 

The AI references a local vector database built from foundational technical analysis books (e.g., John Murphy, Steve Nison) to make highly calculated, mathematically sound trading decisions.

## Architecture Overview

The system runs on a **5-Minute Cron Pipeline**:
1. **Multi-Timeframe Analysis (MTFA):** Fetches 1D, 1H, 15m, and 5m OHLCV data to establish macro trend and micro entry triggers.
2. **Sentiment Analysis:** Integrates global news APIs to validate technical breakouts.
3. **RAG Knowledge Base:** Queries a local ChromaDB containing embedded trading books for historical precedent on the current setup.
4. **AI Synthesizer:** An LLM processes the technicals, sentiment, and book excerpts to propose a trade.
5. **Hard-Coded Risk Manager:** A mathematical circuit breaker that calculates position sizing (1% risk) and verifies R:R before executing via Exchange API or Telegram alert.

## Prerequisites (macOS)

Do not use the built-in macOS Python, as it comes with an outdated SQLite version that is incompatible with ChromaDB.

1. Install Homebrew (if you haven't already):
   `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
2. Install a modern version of Python:
   `brew install python@3.11`

## Setup Instructions

1. **Create the project directory:**
   ```bash
   mkdir ai-trading-agent
   cd ai-trading-agent
   ```

2. **Set up a Virtual Environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   Install the required LangChain packages, vector database, and the necessary async patches:
   ```bash
   pip install langchain langchain-openai langchain-chroma chromadb pypdf python-dotenv langchain-classic "sqlalchemy[asyncio]"
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory and add your OpenAI API key:
   ```text
   OPENAI_API_KEY=sk-your-actual-api-key-here
   ```

## Building the Knowledge Base

We use an **Incremental Indexing** script (`build_knowledge_base.py`). This ensures that if you add new books or backtest logs in the future, it only processes the new files, saving API costs and preventing duplicate data.

1. Create a directory for your source material:
   ```bash
   mkdir trading_books
   ```
2. Drop your PDF books (e.g., *Technical Analysis of the Financial Markets*) into the `trading_books` folder.
3. Run the ingestion script:
   ```bash
   python build_knowledge_base.py
   ```

**Output:**
- `chroma_db/`: The folder containing your vector embeddings.
- `record_manager.sql`: A local SQLite file that fingerprints chunks to prevent re-processing duplicates.

## Next Steps

- Integrate `ccxt` to fetch live Binance/Bybit data.
- Build the Telegram alerting function.
- Implement the mathematical Risk Manager to calculate exact position sizes based on the AI's suggested stop-loss.