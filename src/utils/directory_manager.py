"""
統一目錄管理工具
解決目錄創建重複問題
"""

from pathlib import Path
from typing import Union, List
import logging

logger = logging.getLogger(__name__)


class DirectoryManager:
    """統一的目錄管理工具類"""
    
    @staticmethod
    def ensure_dir(dir_path: Union[str, Path]) -> bool:
        """
        確保目錄存在
        
        Args:
            dir_path: 目錄路徑
        
        Returns:
            bool: 是否成功創建或目錄已存在
        """
        try:
            path = Path(dir_path)
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"創建目錄失敗 {dir_path}: {e}")
            return False
    
    @staticmethod
    def ensure_dirs(dir_paths: List[Union[str, Path]]) -> bool:
        """
        確保多個目錄存在
        
        Args:
            dir_paths: 目錄路徑列表
        
        Returns:
            bool: 是否全部成功
        """
        success = True
        for dir_path in dir_paths:
            if not DirectoryManager.ensure_dir(dir_path):
                success = False
        return success
    
    @staticmethod
    def ensure_parent_dir(file_path: Union[str, Path]) -> bool:
        """
        確保檔案的父目錄存在
        
        Args:
            file_path: 檔案路徑
        
        Returns:
            bool: 是否成功
        """
        try:
            path = Path(file_path)
            return DirectoryManager.ensure_dir(path.parent)
        except Exception as e:
            logger.error(f"創建父目錄失敗 {file_path}: {e}")
            return False
    
    @staticmethod
    def is_dir_writable(dir_path: Union[str, Path]) -> bool:
        """
        檢查目錄是否可寫
        
        Args:
            dir_path: 目錄路徑
        
        Returns:
            bool: 是否可寫
        """
        try:
            path = Path(dir_path)
            if not path.exists():
                return False
            
            # 嘗試創建一個測試檔案
            test_file = path / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_dir_size(dir_path: Union[str, Path]) -> int:
        """
        獲取目錄大小（位元組）
        
        Args:
            dir_path: 目錄路徑
        
        Returns:
            int: 目錄大小
        """
        try:
            path = Path(dir_path)
            if not path.exists() or not path.is_dir():
                return 0
            
            total_size = 0
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        except Exception as e:
            logger.error(f"計算目錄大小失敗 {dir_path}: {e}")
            return 0