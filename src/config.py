import os
import json
import logging
import threading
from pathlib import Path
from typing import Any

class ConfigManager:
    """統一配置管理器"""

    def __init__(self, config_file: str = "config.json", base_dir: Path = None):
        self.config_file = config_file
        self.base_dir = base_dir if base_dir else Path.cwd() # Use current working directory if base_dir not provided
        self._config_cache = None
        self._lock = threading.Lock()
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """統一配置讀取函數"""
        logger = logging.getLogger('whisper_webapp.config')
        logger.debug(f"Attempting to get config key: {key}")
        
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
                    logger.debug(f"Resolved path for {key}")
                    return resolved_path
                logger.debug(f"Found config value for {key}")
                return current_value

        # 回退到環境變數
        logger.debug(f"Key {key} not found in config, checking environment variables")
        return os.getenv(key, default)

    def _load_config(self):
        """載入配置檔案"""
        logger = logging.getLogger('whisper_webapp.config')
        logger.debug("Loading configuration...")
        
        try:
            # config.json is expected to be in the project root, so we use self.base_dir
            config_path = self.base_dir / self.config_file
            logger.debug(f"Checking config path: {config_path}")
            
            if not config_path.exists():
                # Fallback to config.example.json if config.json doesn't exist
                config_path = self.base_dir / "config.example.json"
                logger.info(f"config.json not found, falling back to: {config_path}")

            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
                logger.info(f"Configuration loaded successfully from {config_path}")
            else:
                self._config_cache = {}
                logger.warning(f"No config file found at {config_path}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            self._config_cache = {}

    def reload(self):
        """Reload configuration from disk."""
        with self._lock:
            self._load_config()

    def _set_nested_value(self, data: dict, key: str, value: Any):
        parts = key.split('.')
        current = data
        for part in parts[:-1]:
            nested = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        current[parts[-1]] = value

    def set(self, key: str, value: Any) -> Any:
        """Set and persist a config value."""
        logger = logging.getLogger('whisper_webapp.config')
        with self._lock:
            if not isinstance(self._config_cache, dict):
                self._config_cache = {}

            self._set_nested_value(self._config_cache, key, value)

            config_path = self.base_dir / self.config_file
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_cache, f, ensure_ascii=False, indent=2)
                f.write('\n')

            logger.info(f"Configuration updated for key: {key}")
            return value

# Global instance and getter function
_global_config_manager: ConfigManager = None

def init_config(base_dir: Path):
    global _global_config_manager
    logger = logging.getLogger('whisper_webapp.config')
    logger.debug(f"Initializing ConfigManager with base_dir: {base_dir}")
    
    if _global_config_manager is None:
        _global_config_manager = ConfigManager(base_dir=base_dir)
        logger.info("ConfigManager instance created successfully")
    else:
        logger.debug("ConfigManager already initialized")

def get_config(key: str, default: Any = None) -> Any:
    logger = logging.getLogger('whisper_webapp.config')
    logger.debug(f"Getting config for key: {key}")
    
    if _global_config_manager is None:
        logger.error(f"ConfigManager not initialized when getting key: {key}")
        raise RuntimeError("ConfigManager not initialized. Call init_config() first.")
    return _global_config_manager.get(key, default)

def set_config(key: str, value: Any) -> Any:
    logger = logging.getLogger('whisper_webapp.config')

    if _global_config_manager is None:
        logger.error(f"ConfigManager not initialized when setting key: {key}")
        raise RuntimeError("ConfigManager not initialized. Call init_config() first.")
    return _global_config_manager.set(key, value)

def reload_config():
    logger = logging.getLogger('whisper_webapp.config')

    if _global_config_manager is None:
        logger.error("ConfigManager not initialized when reloading config")
        raise RuntimeError("ConfigManager not initialized. Call init_config() first.")
    _global_config_manager.reload()
