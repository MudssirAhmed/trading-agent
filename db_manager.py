import os
import shutil
import time

def delete_target(path, is_dir=True):
    """Safely deletes a file or directory."""
    try:
        if os.path.exists(path):
            if is_dir:
                shutil.rmtree(path)
                print(f"✅ Successfully deleted folder: {path}/")
            else:
                os.remove(path)
                print(f"✅ Successfully deleted file: {path}")
        else:
            print(f"⚠️ Target not found: {path} (Already deleted or never created)")
    except Exception as e:
        print(f"❌ Error deleting {path}: {e}")

def main():
    while True:
        print("\n" + "="*45)
        print(" 🗄️  AI TRADING AGENT - DATABASE MANAGER")
        print("="*45)
        print("1. Clear 'Theory' DB (Books / chroma_db)")
        print("2. Clear 'Experience' DB (Lessons / experience_db)")
        print("3. Clear Dashboard Trade History (CSV)")
        print("4. ☢️  NUKE EVERYTHING (Reset all memory & history)")
        print("5. Exit")
        print("="*45)
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == '1':
            confirm = input("⚠️ Delete all indexed trading books? You will need to run build_knowledge_base.py again. (y/n): ")
            if confirm.lower() == 'y': 
                delete_target("chroma_db", is_dir=True)
                delete_target("record_manager.sql", is_dir=False) # Clear LangChain's sync record
                
        elif choice == '2':
            confirm = input("⚠️ Delete all past trade reflections and lessons? (y/n): ")
            if confirm.lower() == 'y': 
                delete_target("experience_db", is_dir=True)
                
        elif choice == '3':
            confirm = input("⚠️ Delete the trade history CSV? This resets the Streamlit dashboard. (y/n): ")
            if confirm.lower() == 'y': 
                delete_target("trade_history.csv", is_dir=False)
                
        elif choice == '4':
            confirm = input("🛑 DANGER: Wipe ALL databases, lessons, and trade history? (y/n): ")
            if confirm.lower() == 'y':
                print("\nInitiating complete wipe...")
                time.sleep(1)
                delete_target("chroma_db", is_dir=True)
                delete_target("record_manager.sql", is_dir=False)
                delete_target("experience_db", is_dir=True)
                delete_target("trade_history.csv", is_dir=False)
                print("✨ Complete wipe successful. Clean slate.")
                
        elif choice == '5':
            print("Exiting Manager...")
            break
        else:
            print("Invalid choice. Please enter a number between 1 and 5.")

if __name__ == "__main__":
    main()