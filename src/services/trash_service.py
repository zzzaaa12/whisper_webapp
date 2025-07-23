
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.utils.time_formatter import get_timestamp
from src.utils.file_sanitizer import sanitize_filename

class TrashService:
    """回收桶管理服務"""

    def __init__(self, trash_folder: Path, summary_folder: Path, subtitle_folder: Path):
        self.trash_folder = trash_folder
        self.trash_metadata_file = trash_folder / "metadata.json"
        self.summary_folder = summary_folder
        self.subtitle_folder = subtitle_folder

    def _load_trash_metadata(self) -> list:
        """載入回收桶記錄"""
        try:
            if self.trash_metadata_file.exists():
                with open(self.trash_metadata_file, 'r', encoding='utf-8') as f:
                    return json.loads(f.read())
            return []
        except Exception as e:
            print(f"Error loading trash metadata: {e}")
            return []

    def _save_trash_metadata(self, metadata: list):
        """儲存回收桶記錄"""
        try:
            with open(self.trash_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving trash metadata: {e}")

    def _generate_unique_trash_path(self, file_path: Path, file_type: str) -> Path:
        trash_subfolder = self.trash_folder / file_type
        trash_subfolder.mkdir(parents=True, exist_ok=True)

        timestamp = get_timestamp("file")
        unique_id = str(uuid.uuid4())[:8]
        safe_name = sanitize_filename(file_path.name)
        new_filename = f"{timestamp}_{unique_id}_{safe_name}"
        trash_path = trash_subfolder / new_filename
        return trash_path

    def move_file_to_trash(self, file_path: Path, file_type: str) -> tuple[bool, str]:
        """移動檔案到回收桶"""
        try:
            if not file_path.exists():
                return False, "檔案不存在"

            trash_path = self._generate_unique_trash_path(file_path, file_type)

            shutil.move(str(file_path), str(trash_path))

            metadata = self._load_trash_metadata()
            trash_record = {
                'id': str(uuid.uuid4()),
                'original_path': str(file_path),
                'trash_path': str(trash_path),
                'original_name': file_path.name,
                'file_type': file_type,
                'deleted_at': datetime.now().isoformat(),
                'file_size': trash_path.stat().st_size if trash_path.exists() else 0
            }
            metadata.append(trash_record)
            self._save_trash_metadata(metadata)

            return True, "檔案已移動到回收桶"
        except Exception as e:
            return False, f"移動檔案失敗: {e}"

    def restore_file_from_trash(self, trash_id: str) -> tuple[bool, str]:
        """從回收桶還原檔案"""
        try:
            metadata = self._load_trash_metadata()
            record = None
            record_index = None

            for i, item in enumerate(metadata):
                if item['id'] == trash_id:
                    record = item
                    record_index = i
                    break

            if not record or record_index is None:
                return False, "找不到回收桶記錄"

            trash_path = Path(record['trash_path'])
            if not trash_path.exists():
                return False, "回收桶中的檔案不存在"

            if record['file_type'] == 'summary':
                restore_path = self.summary_folder / sanitize_filename(record['original_name'])
            elif record['file_type'] == 'subtitle':
                restore_path = self.subtitle_folder / sanitize_filename(record['original_name'])
            else:
                return False, "不支援的檔案類型"

            if restore_path.exists():
                timestamp = get_timestamp("file")
                name_parts = restore_path.stem, restore_path.suffix
                restore_path = restore_path.parent / f"{name_parts[0]}_{timestamp}{name_parts[1]}"

            shutil.move(str(trash_path), str(restore_path))

            metadata.pop(record_index)
            self._save_trash_metadata(metadata)

            return True, "檔案已還原"
        except Exception as e:
            return False, f"還原檔案失敗: {e}"

    def delete_file_from_trash(self, trash_id: str) -> tuple[bool, str]:
        """從回收桶永久刪除檔案"""
        try:
            metadata = self._load_trash_metadata()
            record = None
            record_index = None

            for i, item in enumerate(metadata):
                if item['id'] == trash_id:
                    record = item
                    record_index = i
                    break

            if not record or record_index is None:
                return False, "找不到回收桶記錄"

            trash_path = Path(record['trash_path'])
            if trash_path.exists():
                trash_path.unlink()

            metadata.pop(record_index)
            self._save_trash_metadata(metadata)

            return True, "檔案已永久刪除"
        except Exception as e:
            return False, f"刪除檔案失敗: {e}"

    def get_trash_items(self) -> list:
        """獲取回收桶中的所有項目"""
        try:
            metadata = self._load_trash_metadata()
            metadata.sort(key=lambda x: x['deleted_at'], reverse=True)
            return metadata
        except Exception as e:
            print(f"Error getting trash items: {e}")
            return []
