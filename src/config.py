import os
import json
from pathlib import Path
from typing import Any

class ConfigManager:
    """統一配置管理器"""

    def __init__(self, config_file: str = "config.json", base_dir: Path = None):
        self.config_file = config_file
        self.base_dir = base_dir if base_dir else Path.cwd() # Use current working directory if base_dir not provided
        self._config_cache = None
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """統一配置讀取函數"""
        print(f"[ConfigManager.get] Attempting to get key: {key}") # Debug print
        # 檔案配置優先，環境變數次之
        if self._config_cache:
            # Handle nested keys like 'PATHS.DOWNLOADS_DIR'
            parts = key.split('.')
            current_value = self._config_cache
            for part in parts:
                if isinstance(current_value, dict) and part in current_value:
                    current_value = current_value[part]
                else:
                    current_value = None
                    break
            
            if current_value is not None:
                # If it's a path, resolve it relative to base_dir
                if key.startswith("PATHS.") and isinstance(current_value, str):
                    resolved_path = self.base_dir / current_value
                    print(f"[ConfigManager.get] Resolved path for {key}: {resolved_path}") # Debug print
                    return resolved_path
                print(f"[ConfigManager.get] Found value for {key}: {current_value}") # Debug print
                return current_value

        # 回退到環境變數
        print(f"[ConfigManager.get] Key {key} not found in config, checking environment variables.") # Debug print
        return os.getenv(key, default)

    def _load_config(self):
        """載入配置檔案"""
        print(f"[ConfigManager._load_config] Loading config...") # Debug print
        try:
            # config.json is expected to be in the project root, so we use self.base_dir
            config_path = self.base_dir / self.config_file
            print(f"[ConfigManager._load_config] Checking config_path: {config_path}") # Debug print
            if not config_path.exists():
                # Fallback to config.example.json if config.json doesn't exist
                config_path = self.base_dir / "config.example.json"
                print(f"[ConfigManager._load_config] config.json not found, falling back to: {config_path}") # Debug print

            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
                print(f"[ConfigManager._load_config] Config loaded successfully from {config_path}") # Debug print
                # print(f"[ConfigManager._load_config] Config cache: {self._config_cache}") # Uncomment for full config dump
            else:
                self._config_cache = {}
                print(f"[ConfigManager._load_config] No config file found at {config_path}") # Debug print
        except Exception as e:
            print(f"[ConfigManager._load_config] Error loading config file: {e}") # Added for debugging
            self._config_cache = {}

# Global instance and getter function
_global_config_manager: ConfigManager = None

def init_config(base_dir: Path):
    global _global_config_manager
    print(f"[init_config] Initializing ConfigManager with base_dir: {base_dir}") # Debug print
    if _global_config_manager is None:
        _global_config_manager = ConfigManager(base_dir=base_dir)
        print(f"[init_config] ConfigManager instance created: {_global_config_manager}") # Debug print
    else:
        print(f"[init_config] ConfigManager already initialized.") # Debug print

def get_config(key: str, default: Any = None) -> Any:
    print(f"[get_config] Called for key: {key}") # Debug print
    if _global_config_manager is None:
        print(f"[get_config] ERROR: _global_config_manager is None when getting key: {key}") # Debug print
        raise RuntimeError("ConfigManager not initialized. Call init_config() first.")
    return _global_config_manager.get(key, default)