

from typing import Dict, Any

import json
from pathlib import Path
from datetime import datetime

from src.config import get_config
from src.utils.file_sanitizer import sanitize_filename

class BookmarkService:
    """書籤管理服務"""

    def __init__(self, bookmark_file: Path, summary_folder: Path):
        self.bookmark_file = bookmark_file
        self.summary_folder = summary_folder

    def _load_bookmarks_data(self) -> dict:
        """載入書籤資料"""
        try:
            if self.bookmark_file.exists():
                with open(self.bookmark_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {'bookmarks': []}
        except Exception as e:
            print(f"Error loading bookmarks: {e}")
            return {'bookmarks': []}

    def _save_bookmarks_data(self, bookmarks_data: dict) -> bool:
        """儲存書籤資料"""
        try:
            with open(self.bookmark_file, 'w', encoding='utf-8') as f:
                json.dump(bookmarks_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving bookmarks: {e}")
            return False

    def _populate_summary_details(self, bookmark: Dict[str, Any], filename: str):
        try:
            summary_path = self.summary_folder / filename
            if summary_path.exists():
                bookmark['file_size'] = summary_path.stat().st_size
                with open(summary_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')[:3]
                    bookmark['summary_preview'] = '\n'.join(lines)[:200] + ('...' if len(content) > 200 else '')
        except Exception as e:
            print(f"Error reading summary file: {e}")

    def add_bookmark(self, filename: str, title: str = None) -> tuple[bool, str]:
        """新增書籤"""
        try:
            bookmarks_data = self._load_bookmarks_data()
            for bookmark in bookmarks_data['bookmarks']:
                if bookmark['filename'] == filename:
                    return False, "此摘要已在書籤中"
            if not title:
                title = filename.replace('.txt', '').replace('_', ' ')
            bookmark = {
                'filename': filename,
                'title': title,
                'added_date': datetime.now().isoformat(),
                'file_size': 0,
                'summary_preview': ""
            }
            self._populate_summary_details(bookmark, filename)
            bookmarks_data['bookmarks'].append(bookmark)
            self._save_bookmarks_data(bookmarks_data)
            return True, "書籤已新增"
        except Exception as e:
            print(f"Error adding bookmark: {e}")
            return False, f"新增書籤失敗: {e}"

    def remove_bookmark(self, filename: str) -> tuple[bool, str]:
        """移除書籤"""
        try:
            bookmarks_data = self._load_bookmarks_data()
            original_length = len(bookmarks_data['bookmarks'])
            bookmarks_data['bookmarks'] = [
                bookmark for bookmark in bookmarks_data['bookmarks']
                if bookmark['filename'] != filename
            ]
            if len(bookmarks_data['bookmarks']) < original_length:
                self._save_bookmarks_data(bookmarks_data)
                return True, "書籤已移除"
            else:
                return False, "書籤不存在"
        except Exception as e:
            print(f"Error removing bookmark: {e}")
            return False, f"移除書籤失敗: {e}"

    def is_bookmarked(self, filename: str) -> bool:
        """檢查檔案是否已加入書籤"""
        try:
            bookmarks_data = self._load_bookmarks_data()
            return any(bookmark['filename'] == filename for bookmark in bookmarks_data['bookmarks'])
        except Exception as e:
            print(f"Error checking bookmark: {e}")
            return False

    def get_bookmarks(self) -> list:
        """獲取所有書籤"""
        try:
            bookmarks_data = self._load_bookmarks_data()
            bookmarks = bookmarks_data.get('bookmarks', [])
            bookmarks.sort(key=lambda x: x.get('added_date', ''), reverse=True)
            return bookmarks
        except Exception as e:
            print(f"Error getting bookmarks: {e}")
            return []

