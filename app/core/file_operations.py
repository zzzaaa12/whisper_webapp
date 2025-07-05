"""
統一檔案操作管理器
整合所有重複的檔案操作邏輯
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime
import uuid


class FileOperationManager:
    """統一檔案操作管理器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.download_folder = self.base_dir / "downloads"
        self.summary_folder = self.base_dir / "summaries"
        self.subtitle_folder = self.base_dir / "subtitles"
        self.log_folder = self.base_dir / "logs"
        self.trash_folder = self.base_dir / "trash"
        self.upload_folder = self.base_dir / "uploads"
        self.trash_metadata_file = self.trash_folder / "metadata.json"
        
        # 確保目錄存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """確保所有必要目錄存在"""
        directories = [
            self.download_folder,
            self.summary_folder, 
            self.subtitle_folder,
            self.log_folder,
            self.trash_folder,
            self.upload_folder
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def safe_read_text(self, file_path: Union[str, Path], encoding: str = "utf-8") -> str:
        """安全讀取文字檔案"""
        try:
            return Path(file_path).read_text(encoding=encoding)
        except Exception as e:
            raise IOError(f"讀取檔案失敗 {file_path}: {e}")
    
    def safe_write_text(self, file_path: Union[str, Path], content: str, encoding: str = "utf-8") -> bool:
        """安全寫入文字檔案"""
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            return True
        except Exception as e:
            raise IOError(f"寫入檔案失敗 {file_path}: {e}")
    
    def safe_read_json(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """安全讀取 JSON 檔案"""
        try:
            if not Path(file_path).exists():
                return {}
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"讀取 JSON 檔案失敗 {file_path}: {e}")
            return {}
    
    def safe_write_json(self, file_path: Union[str, Path], data: Dict[str, Any]) -> bool:
        """安全寫入 JSON 檔案"""
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"寫入 JSON 檔案失敗 {file_path}: {e}")
            return False
    
    def get_file_size_mb(self, file_path: Union[str, Path]) -> float:
        """取得檔案大小（MB）"""
        try:
            return Path(file_path).stat().st_size / (1024 * 1024)
        except Exception:
            return 0.0
    
    def delete_file_safe(self, file_path: Union[str, Path]) -> bool:
        """安全刪除檔案"""
        try:
            file_path = Path(file_path)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            print(f"刪除檔案失敗 {file_path}: {e}")
            return False
    
    def move_to_trash(self, file_path: Union[str, Path], file_type: str) -> Optional[str]:
        """移動檔案到回收桶"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return None
            
            # 產生回收桶 ID
            trash_id = str(uuid.uuid4())
            
            # 建立回收桶檔案路徑
            trash_file = self.trash_folder / f"{trash_id}_{file_path.name}"
            
            # 移動檔案
            shutil.move(str(file_path), str(trash_file))
            
            # 更新元資料
            metadata = self.load_trash_metadata()
            metadata[trash_id] = {
                'original_path': str(file_path),
                'filename': file_path.name,
                'file_type': file_type,
                'deleted_at': datetime.now().isoformat(),
                'trash_file': str(trash_file)
            }
            self.save_trash_metadata(metadata)
            
            return trash_id
            
        except Exception as e:
            print(f"移動檔案到回收桶失敗: {e}")
            return None
    
    def restore_from_trash(self, trash_id: str) -> bool:
        """從回收桶還原檔案"""
        try:
            metadata = self.load_trash_metadata()
            if trash_id not in metadata:
                return False
            
            item = metadata[trash_id]
            trash_file = Path(item['trash_file'])
            original_path = Path(item['original_path'])
            
            if not trash_file.exists():
                return False
            
            # 確保目標目錄存在
            original_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 還原檔案
            shutil.move(str(trash_file), str(original_path))
            
            # 更新元資料
            del metadata[trash_id]
            self.save_trash_metadata(metadata)
            
            return True
            
        except Exception as e:
            print(f"從回收桶還原檔案失敗: {e}")
            return False
    
    def delete_from_trash(self, trash_id: str) -> bool:
        """從回收桶永久刪除檔案"""
        try:
            metadata = self.load_trash_metadata()
            if trash_id not in metadata:
                return False
            
            item = metadata[trash_id]
            trash_file = Path(item['trash_file'])
            
            # 刪除檔案
            if trash_file.exists():
                trash_file.unlink()
            
            # 更新元資料
            del metadata[trash_id]
            self.save_trash_metadata(metadata)
            
            return True
            
        except Exception as e:
            print(f"從回收桶刪除檔案失敗: {e}")
            return False
    
    def load_trash_metadata(self) -> Dict[str, Any]:
        """載入回收桶元資料"""
        return self.safe_read_json(self.trash_metadata_file)
    
    def save_trash_metadata(self, metadata: Dict[str, Any]) -> bool:
        """儲存回收桶元資料"""
        return self.safe_write_json(self.trash_metadata_file, metadata)
    
    def get_trash_items(self) -> Dict[str, Any]:
        """取得回收桶項目列表"""
        metadata = self.load_trash_metadata()
        trash_items = {}
        
        for trash_id, item in metadata.items():
            # 檢查回收桶檔案是否存在
            trash_file = Path(item['trash_file'])
            if trash_file.exists():
                trash_items[trash_id] = item
        
        return trash_items
    
    def load_bookmarks(self) -> Dict[str, Any]:
        """載入書籤資料"""
        bookmarks_file = self.base_dir / "bookmarks.json"
        return self.safe_read_json(bookmarks_file)
    
    def save_bookmarks(self, bookmarks_data: Dict[str, Any]) -> bool:
        """儲存書籤資料"""
        bookmarks_file = self.base_dir / "bookmarks.json"
        return self.safe_write_json(bookmarks_file, bookmarks_data) 