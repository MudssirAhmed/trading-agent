"""
build_knowledge_base.py
=======================
Ingests NEW trading books from ./trading_books/ into ChromaDB.

Workflow:
  1. Scan ./trading_books/ for PDFs
  2. Embed them with rich metadata (title, author, page)
  3. Use cleanup="incremental" — NEVER deletes previously embedded data
  4. After successful embedding, move each book to ./posted_trading_books/
     so it won't be re-processed on the next run

To add a new book: drop the PDF into ./trading_books/ and run this script.
Old books in ./posted_trading_books/ are already in ChromaDB — safe.
"""

import os
import re
import shutil
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_classic.indexes import SQLRecordManager, index

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

BOOKS_DIR    = "./trading_books"        # Drop new books here
ARCHIVE_DIR  = "./posted_trading_books" # Books move here after embedding
CHROMA_PATH  = "./chroma_db"
RECORD_DB_URL = "sqlite:///record_manager.sql"

# Larger chunks preserve full trading concepts (strategies span paragraphs)
CHUNK_SIZE    = 1500
CHUNK_OVERLAP = 200

# Must match memory_manager.py → book_embeddings model
EMBEDDING_MODEL = "text-embedding-3-large"

# Discard chunks shorter than this (page numbers, headers, etc.)
MIN_CHUNK_LENGTH = 100


# ── Book Metadata Registry ────────────────────────────────────────────────────
# Maps filename fragments → (title, author).
# Add new books here when you expand the library.

BOOK_REGISTRY = {
    "Al Brooks":                     ("Reading Price Charts Bar by Bar",          "Al Brooks"),
    "Market-Wizards":                ("Market Wizards",                           "Jack D. Schwager"),
    "Getting Started in Technical":  ("Getting Started in Technical Analysis",    "Jack D. Schwager"),
    "Japanese Candlestick":          ("Japanese Candlestick Charting Techniques", "Steve Nison"),
    "Technical_Analysis_of_the_Financial_Markets": (
                                     "Technical Analysis of the Financial Markets","John J. Murphy"),
    "Encyclopedia Of Chart Patterns":("Encyclopedia of Chart Patterns",           "Thomas N. Bulkowski"),
    "Trading_in_the_Zone":           ("Trading in the Zone",                      "Mark Douglas"),
    "art and science of technical":  ("The Art and Science of Technical Analysis","Adam Grimes"),
}


def get_book_meta(filepath: str) -> dict:
    """Returns clean title/author metadata for a given PDF filepath."""
    filename = os.path.basename(filepath)
    for key, (title, author) in BOOK_REGISTRY.items():
        if key.lower() in filename.lower():
            return {"book_title": title, "author": author, "source_file": filename}
    # Fallback for unregistered books
    return {"book_title": filename.replace(".pdf", ""), "author": "Unknown", "source_file": filename}


def clean_text(text: str) -> str:
    """Strips PDF noise (page numbers, decorators, excess whitespace)."""
    text = re.sub(r'^\s*\d{1,4}\s*$', '', text, flags=re.MULTILINE)   # lone page numbers
    text = re.sub(r'^\s*[-_=]{3,}\s*$', '', text, flags=re.MULTILINE) # divider lines
    text = re.sub(r'\n{3,}', '\n\n', text)                             # excess newlines
    return text.strip()


def load_single_book(filepath: str) -> list:
    """Loads one PDF, cleans its pages, enriches with metadata. Returns page docs."""
    meta      = get_book_meta(filepath)
    loader    = PyPDFLoader(filepath)
    documents = loader.load()

    for doc in documents:
        doc.metadata.update(meta)
        doc.page_content = clean_text(doc.page_content)

    # Drop near-empty pages (TOC, index, blank pages)
    before    = len(documents)
    documents = [d for d in documents if len(d.page_content) > 80]
    dropped   = before - len(documents)

    print(f"     ✅ {len(documents)} pages loaded ({dropped} empty pages dropped)")
    return documents, meta


def update_knowledge_base():
    print("\n" + "="*55)
    print("  🧠  TRADING KNOWLEDGE BASE — INCREMENTAL UPDATE")
    print("="*55)

    # ── Scan for new books ─────────────────────────────────────────────────────
    if not os.path.exists(BOOKS_DIR):
        print(f"\n❌ Books directory not found: {BOOKS_DIR}")
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)  # ensure archive dir exists

    new_books = sorted([f for f in os.listdir(BOOKS_DIR) if f.endswith(".pdf")])

    if not new_books:
        print(f"\n✅ No new books found in {BOOKS_DIR}/")
        print("   To add a book: drop the PDF into ./trading_books/ and re-run.\n")
        return

    print(f"\n📂 Found {len(new_books)} new book(s) to embed:\n")
    for b in new_books:
        print(f"   • {b}")

    # ── Load and chunk all new books ───────────────────────────────────────────
    all_chunks  = []
    loaded_meta = {}   # filepath → meta (for post-embed move)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
    )

    for filename in new_books:
        filepath = os.path.join(BOOKS_DIR, filename)
        meta     = get_book_meta(filepath)
        print(f"\n  📖 Loading: {meta['book_title']} by {meta['author']}...")

        try:
            documents, meta = load_single_book(filepath)
            chunks = text_splitter.split_documents(documents)

            # Drop noisy short chunks
            before = len(chunks)
            chunks = [c for c in chunks if len(c.page_content.strip()) >= MIN_CHUNK_LENGTH]
            print(f"     ✂️  {len(chunks)} chunks created ({before - len(chunks)} short chunks discarded)")

            all_chunks.extend(chunks)
            loaded_meta[filepath] = meta

        except Exception as e:
            print(f"     ❌ Failed to load {filename}: {e}")
            print("        This book will NOT be moved to archive. Fix and retry.")

    if not all_chunks:
        print("\n❌ No valid chunks produced. Aborting — ChromaDB unchanged.")
        return

    # ── Chunk summary ──────────────────────────────────────────────────────────
    from collections import Counter
    title_counts = Counter(c.metadata.get("book_title", "Unknown") for c in all_chunks)
    print(f"\n📊 Total new chunks to embed: {len(all_chunks)}")
    print("   Breakdown by book:")
    for title, count in title_counts.most_common():
        print(f"   {count:>5} chunks — {title}")

    # ── Embed into ChromaDB ────────────────────────────────────────────────────
    print(f"\n🔗 Connecting to ChromaDB ({EMBEDDING_MODEL})...")
    embeddings  = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

    record_manager = SQLRecordManager(
        f"chroma/{CHROMA_PATH}", db_url=RECORD_DB_URL
    )
    record_manager.create_schema()

    print("\n⚙️  Embedding chunks — this may take several minutes...")
    print("   (cleanup=incremental: existing book data is NEVER deleted)\n")

    result = index(
        all_chunks,
        record_manager,
        vectorstore,
        cleanup="incremental",  # SAFE: only adds new/changed, never deletes old books
        source_id_key="source"
    )

    # ── Results ────────────────────────────────────────────────────────────────
    print("\n" + "="*55)
    print("  ✅  EMBEDDING COMPLETE")
    print("="*55)
    print(f"  Added:   {result.get('num_added',   0):>6} new chunks")
    print(f"  Updated: {result.get('num_updated', 0):>6} chunks")
    print(f"  Skipped: {result.get('num_skipped', 0):>6} unchanged chunks")
    print("="*55)

    # ── Move successfully embedded books to archive ────────────────────────────
    print(f"\n📦 Archiving embedded books → {ARCHIVE_DIR}/")
    for filepath, meta in loaded_meta.items():
        try:
            dest = os.path.join(ARCHIVE_DIR, os.path.basename(filepath))
            shutil.move(filepath, dest)
            print(f"   ✅ Moved: {meta['book_title']}")
        except Exception as e:
            print(f"   ⚠️  Could not move {os.path.basename(filepath)}: {e}")

    print(f"\n✅ Done. trading_books/ is now empty and ready for the next batch.\n")


if __name__ == "__main__":
    update_knowledge_base()