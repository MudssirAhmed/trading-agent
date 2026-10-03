from dotenv import load_dotenv
load_dotenv()  # Must run before initializing OpenAIEmbeddings

from datetime import datetime
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from bot_logger import log_info, log_error, log_warning

# Embeddings must match the model used during ingestion in build_knowledge_base.py
# Books DB: text-embedding-3-large (richer semantic matching for long book passages)
# Experience DB: text-embedding-3-small (lessons are short text, small is sufficient)
book_embeddings       = OpenAIEmbeddings(model="text-embedding-3-large")
experience_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Load databases — each uses its matching embedding model
books_db      = Chroma(persist_directory="./chroma_db",     embedding_function=book_embeddings)
experience_db = Chroma(persist_directory="./experience_db", embedding_function=experience_embeddings)


# ── Semantic Query Builder ────────────────────────────────────────────────────

def _build_semantic_queries(market_state: dict) -> list[str]:
    """
    Converts raw market state into a list of semantic questions that match the
    *language* of trading books. Embedding models work on meaning, not numbers.
    """
    trend       = market_state.get("macro_1D", {}).get("trend", "")
    adx         = market_state.get("macro_1D", {}).get("adx", 0)
    trend_str   = market_state.get("macro_1D", {}).get("trend_strength", "")
    macd_cross  = market_state.get("mid_1H", {}).get("macd_cross", "")
    macd_mom    = market_state.get("mid_1H", {}).get("macd_momentum", "")
    rsi_1h      = market_state.get("mid_1H", {}).get("rsi", 50)
    rsi_5m      = market_state.get("micro_5m", {}).get("rsi", 50)
    rsi_div     = market_state.get("micro_5m", {}).get("rsi_divergence", "None")
    bb_pos      = market_state.get("micro_5m", {}).get("bb_position", "")
    vol_ratio   = market_state.get("micro_5m", {}).get("volume_ratio", 1.0)

    queries = []

    # 1. Trend alignment query
    queries.append(
        f"Trading strategy in a {trend} market trend with ADX {adx:.0f} "
        f"indicating {trend_str} trend strength"
    )

    # 2. MACD momentum query
    queries.append(
        f"MACD {macd_cross} with {macd_mom} histogram momentum on hourly chart "
        f"as entry signal in {trend} trend"
    )

    # 3. RSI + BB entry timing query
    rsi_label = (
        "overbought" if rsi_5m > 70 else
        "oversold"   if rsi_5m < 30 else
        "neutral zone"
    )
    queries.append(
        f"RSI at {rsi_5m:.0f} ({rsi_label}) with price {bb_pos.lower()} "
        f"Bollinger Bands as trade entry trigger"
    )

    # 4. Divergence query (if present)
    if rsi_div != "None":
        queries.append(
            f"{rsi_div} on RSI while price moves opposite — trading divergence signals"
        )

    # 5. Volume confirmation query
    vol_label = "surge" if vol_ratio > 1.5 else ("low" if vol_ratio < 0.7 else "average")
    queries.append(
        f"Volume {vol_label} ({vol_ratio:.1f}x average) during {trend} trend breakout confirmation"
    )

    return queries


def _deduplicate_docs(docs: list) -> list:
    """Remove duplicate page_content chunks."""
    seen = set()
    unique = []
    for doc in docs:
        key = doc.page_content[:100]  # first 100 chars as fingerprint
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


# ── Public Retrieval Functions ────────────────────────────────────────────────

def get_textbook_theory(market_state: dict) -> str:
    """
    Queries the trading books ChromaDB using semantic questions derived from
    the live market state. Uses MMR (Maximal Marginal Relevance) to maximise
    diversity of retrieved chunks (avoids returning 6 near-identical passages).
    Returns up to 6 unique chunks formatted as a numbered reference list.
    """
    log_info("[MEMORY] Consulting trading books with semantic queries...", send_tg=False)

    if isinstance(market_state, str):
        # Legacy fallback: if raw string passed, use it directly
        results = books_db.max_marginal_relevance_search(market_state, k=5, fetch_k=20)
        return "\n\n".join([f"[Book Ref {i+1}] {doc.page_content}" for i, doc in enumerate(results)])

    queries  = _build_semantic_queries(market_state)
    all_docs = []

    for query in queries:
        try:
            # MMR: fetch 15 candidates, return top 3 maximally diverse ones
            docs = books_db.max_marginal_relevance_search(query, k=3, fetch_k=15)
            all_docs.extend(docs)
        except Exception as e:
            log_error(f"[MEMORY] Book DB query failed for '{query[:40]}': {e}", send_tg=False)

    unique_docs = _deduplicate_docs(all_docs)[:8]  # cap at 8 unique passages

    if not unique_docs:
        return "No relevant theory found in knowledge base."

    formatted = "\n\n".join([
        f"[Book Ref {i+1}] {doc.page_content}"
        for i, doc in enumerate(unique_docs)
    ])
    log_info(f"[MEMORY] Retrieved {len(unique_docs)} unique book passages.", send_tg=False)
    return formatted


def get_past_experience(market_state: dict, outcome_filter: str = None) -> str:
    """
    Queries the experience DB for past trade lessons most similar to the current setup.
    
    Args:
        market_state: The structured market state dict (or legacy string).
        outcome_filter: Optional — "WIN" or "LOSS" to filter lessons by outcome.
                        Use "WIN" when looking for entry confirmation patterns.
                        Use "LOSS" when doing risk review.
    Returns formatted lesson list, or a message if empty.
    """
    log_info("[MEMORY] Checking past experiences...", send_tg=False)

    try:
        if isinstance(market_state, str):
            query = market_state
        else:
            queries = _build_semantic_queries(market_state)
            # For experience, combine key signals into a single dense query
            query = " | ".join(queries[:3])

        # Build metadata filter if outcome requested
        where_filter = {"outcome": outcome_filter} if outcome_filter else None

        if where_filter:
            results = experience_db.similarity_search(
                query, k=5, filter=where_filter
            )
        else:
            results = experience_db.similarity_search(query, k=5)

        if not results:
            return "No relevant past experience for this setup."

        formatted_lessons = []
        for i, doc in enumerate(results):
            meta = doc.metadata
            ts   = meta.get("timestamp", "unknown date")
            out  = meta.get("outcome", "unknown")
            conf = meta.get("confidence", "?")
            regime = meta.get("regime", "?")
            formatted_lessons.append(
                f"[Past Trade {i+1} | {out} | {ts} | Confidence: {conf}% | Regime: {regime}]\n"
                f"{doc.page_content}"
            )

        log_info(f"[MEMORY] Retrieved {len(results)} past experience lessons.", send_tg=False)
        return "\n\n".join(formatted_lessons)

    except Exception as e:
        log_error(f"[MEMORY] Experience DB error: {e}", send_tg=False)
        return "Experience DB unavailable."


def save_lesson_to_memory(lesson_text: str, symbol: str, outcome: str,
                          confidence: int, regime: str):
    """
    Saves a validated reflection to the experience database with rich metadata.

    Args:
        lesson_text: The lesson string (must start with 'LESSON:').
        symbol:      Trading pair, e.g. 'BTC/USDT'.
        outcome:     'WIN' or 'LOSS'.
        confidence:  The confidence % used at trade entry.
        regime:      Market regime at trade time, e.g. 'Bullish Strong ADX'.
    """
    # ── Quality Gate 1: Structure check ───────────────────────────────────────
    if not lesson_text.strip().upper().startswith("LESSON:"):
        log_warning("[MEMORY] Lesson rejected — must start with 'LESSON:'. Not saved.", send_tg=False)
        return

    if len(lesson_text.strip()) < 60:
        log_warning(f"[MEMORY] Lesson rejected — too short ({len(lesson_text)} chars). Not saved.", send_tg=False)
        return

    # ── Quality Gate 2: Deduplication check ───────────────────────────────────
    try:
        existing = experience_db.similarity_search(lesson_text, k=1)
        if existing:
            # Very similar lesson already exists — compute rough similarity
            existing_text = existing[0].page_content
            # Simple overlap check (good enough without a full cosine calc)
            overlap = len(set(lesson_text.split()) & set(existing_text.split()))
            total   = len(set(lesson_text.split()))
            similarity = overlap / max(total, 1)
            if similarity > 0.80:
                log_warning("[MEMORY] Lesson skipped — near-duplicate already in experience DB.", send_tg=False)
                return
    except Exception:
        pass  # If dedup check fails, allow save to proceed

    # ── Save with structured metadata ─────────────────────────────────────────
    experience_db.add_texts(
        texts=[lesson_text],
        metadatas=[{
            "symbol":     symbol,
            "type":       "trade_reflection",
            "outcome":    outcome.upper(),
            "confidence": confidence,
            "regime":     regime,
            "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }]
    )
    log_info(f"[MEMORY] ✅ Lesson committed for {symbol} | {outcome} | Regime: {regime}", send_tg=True)