
from pathlib import Path

class FileService:
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

# 便捷函數導出
file_service = FileService()
