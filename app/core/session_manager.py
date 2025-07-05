"""
會話管理器
處理用戶會話、日誌記錄等功能
"""

import threading
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from utils import get_timestamp


class SessionManager:
    """會話管理器"""
    
    def __init__(self, log_folder: Path):
        self.log_folder = Path(log_folder)
        self.log_folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def save_log_entry(self, sid: str, message: str, level: str = 'info'):
        """儲存日誌條目到檔案"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            timestamp = get_timestamp("log")
            log_entry = f"[{timestamp}] {message}\n"

            with self._lock:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
        except Exception as e:
            print(f"Error saving log: {e}")
    
    def get_session_logs(self, sid: str) -> str:
        """取得指定會話的日誌記錄"""
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
        """清除指定會話的日誌記錄"""
        try:
            log_file = self.log_folder / f"session_{sid}.log"
            if log_file.exists():
                log_file.unlink()
        except Exception as e:
            print(f"Error clearing log: {e}")
    
    def cleanup_old_logs(self, max_age_hours: int = 24):
        """清理舊的日誌檔案"""
        try:
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            
            for log_file in self.log_folder.glob("session_*.log"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    
        except Exception as e:
            print(f"Error cleaning up logs: {e}") 