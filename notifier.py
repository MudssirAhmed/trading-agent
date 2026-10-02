import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(message: str):
    """Sends an HTML-formatted message to your Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[NOTIFIER ERROR] Telegram credentials missing in .env")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        # If the message fails, print EXACTLY what Telegram says is wrong
        if response.status_code != 200:
            print(f"[NOTIFIER ERROR] Telegram API Error: {response.status_code} - {response.text}")
            return False
            
        return True
    except Exception as e:
        print(f"[NOTIFIER ERROR] Network connection error: {e}")
        return False