

from pathlib import Path
from datetime import datetime

from src.utils.time_formatter import get_timestamp

class LogService:
    """日誌服務，負責日誌的儲存與讀取"""

    def __init__(self, log_folder: Path):
        self.log_folder = log_folder
        self.log_folder.mkdir(parents=True, exist_ok=True)

    def save_log_entry(self, sid: str, message: str, level: str = 'info'):
        """將日誌條目儲存到檔案"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            timestamp = get_timestamp("log")
            log_entry = f"[{timestamp}] {message}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error saving log: {e}")

    def get_session_logs(self, sid: str) -> str:
        """獲取指定 session 的日誌記錄"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"Error reading log: {e}")
            return ""

    def clear_session_logs(self, sid: str):
        """清除指定 session 的日誌記錄"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            if log_file.exists():
                log_file.unlink()
        except Exception as e:
            print(f"Error clearing log: {e}")

