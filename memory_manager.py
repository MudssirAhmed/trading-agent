from dotenv import load_dotenv
load_dotenv()  # Must run before initializing OpenAIEmbeddings

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# Initialize embeddings once
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Load databases
books_db = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
experience_db = Chroma(persist_directory="./experience_db", embedding_function=embeddings)

def get_textbook_theory(market_context_string):
    """Queries the trading books database."""
    print("[MEMORY] Consulting trading books...")
    results = books_db.similarity_search(market_context_string, k=2)
    return "\n".join([doc.page_content for doc in results])

def get_past_experience(market_context_string):
    """Queries the bot's past lessons learned."""
    print("[MEMORY] Checking past experiences...")
    try:
        results = experience_db.similarity_search(market_context_string, k=2)
        return "\n".join([doc.page_content for doc in results]) if results else "No relevant past experience."
    except Exception:
        return "Experience DB is currently empty."

def save_lesson_to_memory(lesson_text, symbol):
    """Saves a new reflection to the experience database."""
    experience_db.add_texts(
        texts=[lesson_text],
        metadatas=[{"symbol": symbol, "type": "trade_reflection"}]
    )
    print(f"[MEMORY] Lesson permanently committed for {symbol}.")