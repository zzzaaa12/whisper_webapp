

from pathlib import Path
from datetime import datetime

from src.utils.time_formatter import get_timestamp
from src.utils.logger_manager import get_logger_manager

class LogService:
    """日誌服務，負責日誌的儲存與讀取"""

    def __init__(self, log_folder: Path):
        self.log_folder = log_folder
        self.log_folder.mkdir(parents=True, exist_ok=True)
        self.logger_manager = get_logger_manager()

    def save_log_entry(self, sid: str, message: str, level: str = 'info'):
        """將日誌條目儲存到檔案"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            timestamp = get_timestamp("log")
            log_entry = f"[{timestamp}] {message}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

            # 同時記錄到統一日誌系統
            self.logger_manager.info(f"[Session:{sid}] {message}", "socketio")

        except Exception as e:
            # 使用統一日誌系統記錄錯誤
            self.logger_manager.error(f"Error saving session log for {sid}: {e}", "log_service")

    def get_session_logs(self, sid: str) -> str:
        """獲取指定 session 的日誌記錄"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            # 使用統一日誌系統記錄錯誤
            self.logger_manager.error(f"Error reading session log for {sid}: {e}", "log_service")
            return ""

    def clear_session_logs(self, sid: str):
        """清除指定 session 的日誌記錄"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            if log_file.exists():
                log_file.unlink()
                self.logger_manager.info(f"Cleared session log for {sid}", "log_service")
        except Exception as e:
            # 使用統一日誌系統記錄錯誤
            self.logger_manager.error(f"Error clearing session log for {sid}: {e}", "log_service")

    def get_all_session_logs(self) -> dict:
        """獲取所有session的日誌記錄"""
        try:
            session_logs = {}
            for log_file in self.log_folder.glob("session_*.log"):
                sid = log_file.stem.replace("session_", "")
                session_logs[sid] = self.get_session_logs(sid)
            return session_logs
        except Exception as e:
            self.logger_manager.error(f"Error getting all session logs: {e}", "log_service")
            return {}

    def cleanup_old_logs(self, max_age_days: int = 7):
        """清理超過指定天數的舊日誌"""
        try:
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(days=max_age_days)

            cleaned_count = 0
            for log_file in self.log_folder.glob("session_*.log"):
                if log_file.stat().st_mtime < cutoff_time.timestamp():
                    log_file.unlink()
                    cleaned_count += 1

            if cleaned_count > 0:
                self.logger_manager.info(f"Cleaned {cleaned_count} old session log files", "log_service")

        except Exception as e:
            self.logger_manager.error(f"Error cleaning old logs: {e}", "log_service")

