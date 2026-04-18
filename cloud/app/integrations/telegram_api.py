from typing import Optional, Tuple


def download_telegram_file_bytes(telegram_bot, file_id: str) -> Optional[Tuple[bytes, str]]:
    """Download Telegram file bytes. Returns (bytes, file_path) or None."""
    try:
        file_info = telegram_bot.get_file(file_id)
        data = telegram_bot.download_file(file_info.file_path)
        return data, file_info.file_path
    except Exception as e:
        print(f"[Telegram] ❌ File download failed: {e}")
        return None