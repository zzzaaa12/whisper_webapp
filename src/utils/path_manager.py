"""
統一路徑管理器
解決路徑定義重複問題
"""

from pathlib import Path
from typing import Optional
from src.config import get_config


class PathManager:
    """統一的路徑管理器 - 單例模式"""
    
    _instance: Optional['PathManager'] = None
    
    def __init__(self):
        if PathManager._instance is not None:
            raise RuntimeError("PathManager is a singleton. Use get_instance() instead.")
        
        # 基礎目錄
        self.base_dir = Path(__file__).parent.parent.parent.resolve()
        
        # 從配置獲取路徑，如果配置不存在則使用預設值
        self.downloads_dir = self._get_path_from_config('PATHS.DOWNLOADS_DIR', 'downloads')
        self.summaries_dir = self._get_path_from_config('PATHS.SUMMARIES_DIR', 'summaries')
        self.subtitles_dir = self._get_path_from_config('PATHS.SUBTITLES_DIR', 'subtitles')
        self.uploads_dir = self._get_path_from_config('PATHS.UPLOADS_DIR', 'uploads')
        self.trash_dir = self._get_path_from_config('PATHS.TRASH_DIR', 'trash')
        self.logs_dir = self._get_path_from_config('PATHS.LOGS_DIR', 'logs')
        self.tasks_dir = self._get_path_from_config('PATHS.TASKS_DIR', 'tasks')
        self.certs_dir = self._get_path_from_config('PATHS.CERTS_DIR', 'certs')
        
        # 特殊檔案路徑
        self.bookmark_file = self.base_dir / "bookmarks.json"
    
    def _get_path_from_config(self, config_key: str, default_name: str) -> Path:
        """從配置獲取路徑，如果是相對路徑則基於base_dir"""
        try:
            path_value = get_config(config_key, default_name)
            if isinstance(path_value, Path):
                # 如果配置管理器已經返回了絕對路徑
                return path_value
            else:
                # 如果是字串，則基於base_dir構建
                return self.base_dir / path_value
        except Exception:
            # 如果配置讀取失敗，使用預設值
            return self.base_dir / default_name
    
    @classmethod
    def get_instance(cls) -> 'PathManager':
        """獲取單例實例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置實例（主要用於測試）"""
        cls._instance = None
    
    def ensure_all_dirs(self):
        """確保所有目錄存在"""
        dirs_to_create = [
            self.downloads_dir,
            self.summaries_dir,
            self.subtitles_dir,
            self.uploads_dir,
            self.trash_dir,
            self.logs_dir,
            self.tasks_dir,
            self.certs_dir,
            self.trash_dir / "summaries",
            self.trash_dir / "subtitles"
        ]
        
        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def get_summary_folder(self) -> Path:
        """獲取摘要資料夾路徑"""
        return self.summaries_dir
    
    def get_subtitle_folder(self) -> Path:
        """獲取字幕資料夾路徑"""
        return self.subtitles_dir
    
    def get_trash_folder(self) -> Path:
        """獲取回收桶資料夾路徑"""
        return self.trash_dir
    
    def get_bookmark_file(self) -> Path:
        """獲取書籤檔案路徑"""
        return self.bookmark_file
    
    def get_uploads_folder(self) -> Path:
        """獲取上傳資料夾路徑"""
        return self.uploads_dir


# 便捷函數
def get_path_manager() -> PathManager:
    """獲取路徑管理器實例"""
    return PathManager.get_instance()