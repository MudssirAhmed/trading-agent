import logging
from notifier import send_telegram_log

# Configure file and console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("engine.log"),
        logging.StreamHandler()
    ]
)

def log_info(message: str, send_tg: bool = False):
    """Log info to file, console, and optionally Telegram."""
    logging.info(message)
    if send_tg:
        send_telegram_log(f"ℹ️ <b>INFO:</b>\n{message}")

def log_error(message: str, send_tg: bool = True):
    """Log error to file, console, and Telegram."""
    logging.error(message)
    if send_tg:
        send_telegram_log(f"❌ <b>ERROR:</b>\n{message}")

def log_warning(message: str, send_tg: bool = True):
    """Log warning to file, console, and Telegram."""
    logging.warning(message)
    if send_tg:
        send_telegram_log(f"⚠️ <b>WARNING:</b>\n{message}")
