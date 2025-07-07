
import os
import json
from pathlib import Path
from typing import Any

class ConfigManager:
    """統一配置管理器"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self._config_cache = None
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """統一配置讀取函數"""
        # 檔案配置優先，環境變數次之
        if self._config_cache and key in self._config_cache:
            return self._config_cache[key]

        # 回退到環境變數
        return os.getenv(key, default)

    def _load_config(self):
        """載入配置檔案"""
        try:
            config_path = Path(__file__).parent.parent / self.config_file
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
            else:
                self._config_cache = {}
        except Exception:
            self._config_cache = {}

# 全域單例實例
_config_manager = ConfigManager()

def get_config(key: str, default: Any = None) -> Any:
    """便捷配置讀取函數"""
    return _config_manager.get(key, default)
