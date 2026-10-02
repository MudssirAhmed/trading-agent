import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_classic.indexes import SQLRecordManager, index
from dotenv import load_dotenv

load_dotenv()

BOOKS_DIR = "./trading_books"
CHROMA_PATH = "./chroma_db"
# This is the new database that tracks what has already been processed
RECORD_DB_URL = "sqlite:///record_manager.sql"

def update_knowledge_base():
    all_documents = []
    
    # 1. Load PDFs
    for filename in os.listdir(BOOKS_DIR):
        if filename.endswith(".pdf"):
            file_path = os.path.join(BOOKS_DIR, filename)
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            all_documents.extend(documents)
            
    # 2. Split the text
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=70)
    chunks = text_splitter.split_documents(all_documents)
    
    # 3. Setup Vectorstore & Embeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    
    # 4. Initialize the Record Manager
    # This prevents duplication and manages future updates
    record_manager = SQLRecordManager(
        f"chroma/{CHROMA_PATH}", db_url=RECORD_DB_URL
    )
    record_manager.create_schema()
    
    print("Syncing documents... (This only embeds NEW or CHANGED data)")
    
    # 5. Run the Incremental Index
    result = index(
        chunks,
        record_manager,
        vectorstore,
        cleanup="incremental",
        source_id_key="source"
    )
    
    # This will print exactly what happened (e.g., {'num_added': 500, 'num_skipped': 15000})
    print(f"Sync complete: {result}")

if __name__ == "__main__":
    update_knowledge_base()