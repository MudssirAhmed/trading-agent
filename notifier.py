import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_LOGGER_TOKEN = os.getenv("TELEGRAM_LOGGER_BOT_TOKEN")
TELEGRAM_LOGGER_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(message: str):
    """Sends an HTML-formatted message to your Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("[NOTIFIER ERROR] Telegram credentials missing in .env")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"[NOTIFIER ERROR] Telegram API Error: {response.status_code} - {response.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"[NOTIFIER ERROR] Network connection error: {e}")
        return False

def send_telegram_log(message: str):
    """Sends an HTML-formatted log message to the logger Telegram chat."""
    if not TELEGRAM_LOGGER_TOKEN or not TELEGRAM_LOGGER_CHAT_ID:
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_LOGGER_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_LOGGER_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception:
        # Ignore logging errors so we don't create an infinite loop of error logging
        return False