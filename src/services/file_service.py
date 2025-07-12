import os
import uuid
from pathlib import Path
from werkzeug.datastructures import FileStorage

from src.config import get_config
from task_queue import get_task_queue
from src.utils.file_sanitizer import sanitize_filename
from src.utils.time_formatter import get_timestamp

class FileService:
    """統一檔案操作工具"""

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent.resolve()
        self.upload_folder = self.base_dir / "uploads"
        self.subtitle_folder = self.base_dir / "subtitles"
        self.summary_folder = self.base_dir / "summaries"
        self.max_file_size = 500 * 1024 * 1024  # 500MB
        self.allowed_extensions = {
            '.mp3', '.mp4', '.wav', '.m4a', '.flv', '.avi', '.mov',
            '.mkv', '.webm', '.ogg', '.aac', '.wma', '.wmv', '.3gp'
        }

    def save_uploaded_media(self, file: FileStorage, user_ip: str) -> dict:
        """
        處理上傳的媒體檔案，包括驗證、儲存和建立處理任務。
        """
        # 1. 驗證檔案
        if not file or file.filename == '':
            return {'success': False, 'message': '沒有選擇檔案', 'status_code': 400}

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        if file_size > self.max_file_size:
            message = f'檔案過大，最大限制 500MB，目前檔案 {file_size / (1024*1024):.1f}MB'
            return {'success': False, 'message': message, 'status_code': 413}

        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_extensions:
            message = f'不支援的檔案格式：{file_ext}。支援格式：{", ".join(sorted(self.allowed_extensions))}'
            return {'success': False, 'message': message, 'status_code': 400}

        # 2. 產生安全檔名並儲存
        original_title = os.path.splitext(file.filename)[0]
        timestamp = get_timestamp("file")
        safe_title = sanitize_filename(original_title) if original_title else "未命名"
        task_id_short = str(uuid.uuid4())[:8]
        safe_filename = f"{timestamp}_{task_id_short}_{safe_title}{file_ext}"

        self.ensure_dir(self.upload_folder)
        file_path = self.upload_folder / safe_filename
        file.save(str(file_path))

        # 3. 準備任務資料
        date_str = get_timestamp("date")
        base_name = f"{date_str} - {safe_title}"
        subtitle_path = self.subtitle_folder / f"{base_name}.srt"
        summary_path = self.summary_folder / f"{base_name}.txt"

        task_data = {
            'audio_file': str(file_path),
            'subtitle_path': str(subtitle_path),
            'summary_path': str(summary_path),
            'title': original_title or safe_title,
            'filename': safe_filename
        }

        # 4. 加入處理佇列
        queue_manager = get_task_queue()
        queue_task_id = queue_manager.add_task('upload_media', task_data, priority=5, user_ip=user_ip)
        queue_position = queue_manager.get_user_queue_position(queue_task_id)

        return {
            'success': True,
            'message': '檔案上傳成功，已加入處理佇列',
            'task_id': queue_task_id,
            'queue_position': queue_position,
            'filename': safe_filename,
            'title': original_title or safe_title,
            'file_size': file_size,
        }


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