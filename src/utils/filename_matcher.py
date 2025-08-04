"""
檔名比對工具 - 處理日期前綴的檔名比對邏輯
"""

import re
from pathlib import Path
from typing import List, Optional


class FilenameMatcher:
    """檔名比對器 - 專門處理帶日期前綴的檔名比對"""

    @staticmethod
    def extract_content_part(filename: str) -> str:
        """
        提取檔名中日期後的內容部分

        Args:
            filename: 檔案名稱（可包含副檔名）

        Returns:
            str: 日期後的內容部分，如果格式不符則返回原檔名

        Examples:
            "2025.11.22 - AI技術發展.txt" -> "AI技術發展"
            "2025.01.15 - [Auto] 區塊鏈應用.srt" -> "[Auto] 區塊鏈應用"
            "不符合格式的檔名.txt" -> "不符合格式的檔名"
        """
        # 移除副檔名
        stem = Path(filename).stem

        # 檢查是否符合日期格式：YYYY.MM.DD -
        date_pattern = r'^\d{4}\.\d{2}\.\d{2} - '
        match = re.match(date_pattern, stem)

        if match:
            # 提取日期後的部分（第14個字以後）
            date_prefix_length = len(match.group(0))  # "2025.11.22 - " 的長度是 13
            content_part = stem[date_prefix_length:].strip()
            # 如果內容部分為空，返回原檔名
            return content_part if content_part else stem
        else:
            # 如果不符合日期格式，返回原檔名（去除副檔名）
            return stem

    @staticmethod
    def is_content_match(filename1: str, filename2: str) -> bool:
        """
        比對兩個檔名的內容部分是否相同（忽略日期前綴）

        Args:
            filename1: 第一個檔名
            filename2: 第二個檔名

        Returns:
            bool: 內容部分是否相同
        """
        content1 = FilenameMatcher.extract_content_part(filename1)
        content2 = FilenameMatcher.extract_content_part(filename2)

        return content1 == content2

    @staticmethod
    def find_matching_files(target_filename: str, search_directory: Path,
                          file_extensions: List[str] = None) -> List[Path]:
        """
        在指定目錄中尋找內容部分相同的檔案

        Args:
            target_filename: 目標檔名
            search_directory: 搜尋目錄
            file_extensions: 要搜尋的副檔名列表，如 ['.txt', '.srt']

        Returns:
            List[Path]: 找到的相同內容檔案列表
        """
        if not search_directory.exists():
            return []

        target_content = FilenameMatcher.extract_content_part(target_filename)
        matching_files = []

        # 如果沒有指定副檔名，搜尋所有檔案
        if file_extensions is None:
            search_pattern = '*'
        else:
            search_pattern = '*'

        for file_path in search_directory.glob(search_pattern):
            if not file_path.is_file():
                continue

            # 如果指定了副檔名，檢查是否符合
            if file_extensions and file_path.suffix.lower() not in [ext.lower() for ext in file_extensions]:
                continue

            file_content = FilenameMatcher.extract_content_part(file_path.name)
            if file_content == target_content:
                matching_files.append(file_path)

        return matching_files

    @staticmethod
    def find_existing_audio_file(video_title: str, download_directory: Path) -> Optional[Path]:
        """
        在下載目錄中尋找相同內容的音訊檔案

        Args:
            video_title: 影片標題
            download_directory: 下載目錄

        Returns:
            Optional[Path]: 找到的音訊檔案路徑，沒找到則返回 None
        """
        if not download_directory.exists():
            return None

        # 常見的音訊檔案副檔名
        audio_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac']

        for file_path in download_directory.glob('*'):
            if not file_path.is_file():
                continue

            # 檢查是否為音訊檔案
            if file_path.suffix.lower() not in audio_extensions:
                continue

            # 檢查檔名中是否包含影片標題（原有邏輯）
            if video_title in file_path.stem:
                return file_path

        return None


# 便捷函數
def extract_filename_content(filename: str) -> str:
    """便捷函數：提取檔名內容部分"""
    return FilenameMatcher.extract_content_part(filename)


def is_same_content_file(filename1: str, filename2: str) -> bool:
    """便捷函數：比對檔名內容是否相同"""
    return FilenameMatcher.is_content_match(filename1, filename2)


def find_duplicate_files(target_filename: str, search_directory: Path,
                        extensions: List[str] = None) -> List[Path]:
    """便捷函數：尋找重複內容的檔案"""
    return FilenameMatcher.find_matching_files(target_filename, search_directory, extensions)