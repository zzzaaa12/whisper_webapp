"""
統一日誌管理器
解決日誌系統重複和不一致問題
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Any
from enum import Enum


class LogLevel(Enum):
    """日誌等級枚舉"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LoggerManager:
    """統一的日誌管理器"""
    
    _instance: Optional['LoggerManager'] = None
    
    def __init__(self, log_dir: Optional[Path] = None, enable_console: bool = True):
        if LoggerManager._instance is not None:
            raise RuntimeError("LoggerManager is a singleton. Use get_instance() instead.")
        
        self.log_dir = log_dir or Path("logs")
        self.enable_console = enable_console
        self.loggers = {}
        
        # 確保日誌目錄存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 設置根日誌器
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """設置根日誌器"""
        # 創建根日誌器
        self.root_logger = logging.getLogger('whisper_webapp')
        self.root_logger.setLevel(logging.DEBUG)
        
        # 清除現有的處理器
        self.root_logger.handlers.clear()
        
        # 創建格式器
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 添加檔案處理器
        file_handler = logging.FileHandler(
            self.log_dir / 'whisper_webapp.log',
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.root_logger.addHandler(file_handler)
        
        # 添加控制台處理器（如果啟用）
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.root_logger.addHandler(console_handler)
    
    @classmethod
    def get_instance(cls, log_dir: Optional[Path] = None, enable_console: bool = True) -> 'LoggerManager':
        """獲取單例實例"""
        if cls._instance is None:
            cls._instance = cls(log_dir, enable_console)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置實例（主要用於測試）"""
        cls._instance = None
    
    def get_logger(self, name: str) -> logging.Logger:
        """獲取指定名稱的日誌器"""
        if name not in self.loggers:
            logger = logging.getLogger(f'whisper_webapp.{name}')
            self.loggers[name] = logger
        return self.loggers[name]
    
    def debug(self, message: str, module: str = "system"):
        """記錄DEBUG等級日誌"""
        logger = self.get_logger(module)
        logger.debug(message)
    
    def info(self, message: str, module: str = "system"):
        """記錄INFO等級日誌"""
        logger = self.get_logger(module)
        logger.info(message)
    
    def warning(self, message: str, module: str = "system"):
        """記錄WARNING等級日誌"""
        logger = self.get_logger(module)
        logger.warning(message)
    
    def error(self, message: str, module: str = "system"):
        """記錄ERROR等級日誌"""
        logger = self.get_logger(module)
        logger.error(message)
    
    def critical(self, message: str, module: str = "system"):
        """記錄CRITICAL等級日誌"""
        logger = self.get_logger(module)
        logger.critical(message)


class LogCallback:
    """標準化的日誌回調類"""
    
    def __init__(self, module: str, task_id: Optional[str] = None, 
                 socketio_callback: Optional[Callable] = None):
        self.module = module
        self.task_id = task_id
        self.socketio_callback = socketio_callback
        self.logger_manager = LoggerManager.get_instance()
    
    def __call__(self, message: str, level: str = 'info'):
        """日誌回調函數"""
        # 標準化日誌等級
        level = level.upper()
        if level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            level = 'INFO'
        
        # 添加任務ID前綴（如果有）
        if self.task_id:
            message = f"[Task:{self.task_id}] {message}"
        
        # 記錄到日誌系統
        if level == 'DEBUG':
            self.logger_manager.debug(message, self.module)
        elif level == 'INFO':
            self.logger_manager.info(message, self.module)
        elif level == 'WARNING':
            self.logger_manager.warning(message, self.module)
        elif level == 'ERROR':
            self.logger_manager.error(message, self.module)
        elif level == 'CRITICAL':
            self.logger_manager.critical(message, self.module)
        
        # 發送到SocketIO（如果有回調）
        if self.socketio_callback:
            try:
                self.socketio_callback(message, level.lower())
            except Exception as e:
                self.logger_manager.error(f"SocketIO callback failed: {e}", "logger")


# 便捷函數
def get_logger_manager() -> LoggerManager:
    """獲取日誌管理器實例"""
    return LoggerManager.get_instance()


def create_log_callback(module: str, task_id: Optional[str] = None, 
                       socketio_callback: Optional[Callable] = None) -> LogCallback:
    """創建標準化的日誌回調"""
    return LogCallback(module, task_id, socketio_callback)


def setup_logging(log_dir: Optional[Path] = None, enable_console: bool = True):
    """初始化日誌系統"""
    LoggerManager.get_instance(log_dir, enable_console)