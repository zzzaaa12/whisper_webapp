"""
統一工具函數模組 - 整合所有重複的核心功能
"""

import os
import re
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable


class ConfigManager:
    """統一配置管理器"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self._config_cache = None

    def get_config(self, key: str, default: Any = None) -> Any:
        """統一配置讀取函數"""
        # 先嘗試從檔案讀取
        if self._config_cache is None:
            self._load_config()

        # 檔案配置優先，環境變數次之
        if self._config_cache and key in self._config_cache:
            return self._config_cache[key]

        # 回退到環境變數
        return os.getenv(key, default)

    def _load_config(self):
        """載入配置檔案"""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
            else:
                self._config_cache = {}
        except Exception:
            self._config_cache = {}


class FileNameSanitizer:
    """統一檔案名清理器"""

    @staticmethod
    def sanitize(filename: str, max_length: int = 80) -> str:
        """統一檔案名清理函數"""
        if not filename:
            return "unknown"

        original = filename

        # 1. 移除 Windows 禁用字元
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

        # 2. 移除常見特殊符號（但保留中文、數字、字母）
        filename = re.sub(r'[\[\]{}()!@#$%^&+=~`]', '_', filename)

        # 3. 移除表情符號和其他 Unicode 符號（保留中文字元）
        filename = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf\w\s\-_.]', '_', filename, flags=re.UNICODE)

        # 4. 處理多重空格和底線
        filename = re.sub(r'\s+', '_', filename)
        filename = re.sub(r'_+', '_', filename)

        # 5. 移除開頭和結尾的特殊字元
        filename = filename.strip('._')

        # 6. 長度處理（考慮中文字元）
        if len(filename.encode('utf-8')) > max_length * 2:
            if max_length > 20:
                # 智能截斷：保留前 60% 和後面部分
                keep_start = int(max_length * 0.6)
                keep_end = max_length - keep_start - 3

                safe_start = filename[:keep_start].encode('utf-8')[:keep_start*2].decode('utf-8', errors='ignore')
                safe_end = filename[-keep_end:].encode('utf-8')[-keep_end*2:].decode('utf-8', errors='ignore') if keep_end > 0 else ""

                filename = safe_start + "..." + safe_end
            else:
                filename = filename.encode('utf-8')[:max_length].decode('utf-8', errors='ignore')

        result = filename if filename else "unknown"
        return result


class SRTConverter:
    """統一SRT字幕轉換器"""

    @staticmethod
    def segments_to_srt(segments) -> str:
        """統一字幕轉換函數"""
        def format_timestamp(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds - int(seconds)) * 1000)
            return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

        srt_lines = []
        for idx, segment in enumerate(segments, 1):
            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)
            text = segment.text.strip()
            srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

        return "\n".join(srt_lines)


class TimeFormatter:
    """統一時間格式化器"""

    @staticmethod
    def get_timestamp(format_type: str = "default") -> str:
        """統一時間格式化函數"""
        now = datetime.now()

        formats = {
            "default": "%Y-%m-%d %H:%M:%S",
            "log": "%m/%d %H:%M:%S",
            "file": "%Y%m%d_%H%M%S",
            "date": "%Y.%m.%d",
            "display": "%Y-%m-%d %H:%M:%S"
        }

        return now.strftime(formats.get(format_type, formats["default"]))


class FileOperations:
    """統一檔案操作工具"""

    @staticmethod
    def safe_read_text(file_path: Path, encoding: str = "utf-8") -> str:
        """安全讀取文字檔案"""
        try:
            return file_path.read_text(encoding=encoding)
        except Exception as e:
            raise IOError(f"讀取檔案失敗 {file_path}: {e}")

    @staticmethod
    def safe_write_text(file_path: Path, content: str, encoding: str = "utf-8") -> bool:
        """安全寫入文字檔案"""
        try:
            # 確保目錄存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            return True
        except Exception as e:
            raise IOError(f"寫入檔案失敗 {file_path}: {e}")

    @staticmethod
    def ensure_dir(dir_path: Path) -> None:
        """確保目錄存在"""
        dir_path.mkdir(parents=True, exist_ok=True)


class NotificationService:
    """統一通知服務"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def send_telegram_notification(self, message: str) -> bool:
        """統一Telegram通知函數"""
        bot_token = self.config.get_config('TELEGRAM_BOT_TOKEN')
        chat_id = self.config.get_config('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            print("[NOTIFICATION] Telegram credentials not set. Skipping notification.")
            return False

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        try:
            response = requests.post(api_url, data=payload, timeout=5)
            if response.status_code == 200:
                return True
            else:
                print(f"[NOTIFICATION] Error sending Telegram message: {response.text}")
                return False
        except Exception as e:
            print(f"[NOTIFICATION] Exception while sending Telegram message: {e}")
            return False


class ExceptionHandler:
    """統一異常處理器"""

    @staticmethod
    def safe_execute(func: Callable, error_callback: Optional[Callable] = None, default_return: Any = None):
        """統一異常處理包裝器"""
        try:
            return func()
        except Exception as e:
            if error_callback:
                error_callback(f"操作失敗: {e}")
            return default_return

    @staticmethod
    def log_exception(operation: str, exception: Exception, logger_func: Optional[Callable] = None):
        """統一異常記錄"""
        error_msg = f"[ERROR] {operation} 失敗: {exception}"

        if logger_func:
            logger_func(error_msg, 'error')
        else:
            print(error_msg)


class AccessValidator:
    """統一通行碼驗證器"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def validate_access_code(self, user_code: str) -> bool:
        """統一通行碼驗證函數"""
        system_access_code = self.config.get_config("ACCESS_CODE")

        if not system_access_code:
            return True  # 未設定通行碼時允許通過

        return user_code.strip().lower() == system_access_code.strip().lower()


# 全域單例實例
config_manager = ConfigManager()
file_sanitizer = FileNameSanitizer()
srt_converter = SRTConverter()
time_formatter = TimeFormatter()
file_ops = FileOperations()
notification_service = NotificationService(config_manager)
exception_handler = ExceptionHandler()
access_validator = AccessValidator(config_manager)


# 便捷函數導出
def get_config(key: str, default: Any = None) -> Any:
    """便捷配置讀取函數"""
    return config_manager.get_config(key, default)


def sanitize_filename(filename: str, max_length: int = 80) -> str:
    """便捷檔案名清理函數"""
    return file_sanitizer.sanitize(filename, max_length)


def segments_to_srt(segments) -> str:
    """便捷SRT轉換函數"""
    return srt_converter.segments_to_srt(segments)


def get_timestamp(format_type: str = "default") -> str:
    """便捷時間格式化函數"""
    return time_formatter.get_timestamp(format_type)


def send_telegram_notification(message: str) -> bool:
    """便捷Telegram通知函數"""
    return notification_service.send_telegram_notification(message)


def validate_access_code(user_code: str) -> bool:
    """便捷通行碼驗證函數"""
    return access_validator.validate_access_code(user_code)