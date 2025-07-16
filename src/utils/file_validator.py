"""
統一檔案安全驗證工具
解決檔案路徑驗證重複問題
"""

from pathlib import Path
from typing import Tuple, Optional
from urllib.parse import unquote


class FileValidator:
    """檔案安全驗證工具類"""
    
    @staticmethod
    def validate_safe_path(filename: str, allowed_folder: Path, 
                          allowed_extensions: Optional[set] = None) -> Tuple[bool, str, Optional[Path]]:
        """
        統一的檔案路徑安全驗證
        
        Args:
            filename: 檔案名稱
            allowed_folder: 允許的資料夾路徑
            allowed_extensions: 允許的副檔名集合（可選）
        
        Returns:
            tuple: (是否有效, 錯誤訊息, 安全路徑)
        """
        try:
            # URL 解碼檔案名稱
            decoded_filename = unquote(filename)
            
            # 構建安全路徑
            safe_path = (allowed_folder / decoded_filename).resolve()
            allowed_folder_resolved = allowed_folder.resolve()
            
            # 檢查路徑是否在允許的資料夾內
            if not str(safe_path).startswith(str(allowed_folder_resolved)):
                return False, "檔案路徑無效", None
            
            # 檢查檔案是否存在
            if not safe_path.exists():
                return False, "檔案不存在", None
            
            # 檢查副檔名（如果指定）
            if allowed_extensions and safe_path.suffix.lower() not in allowed_extensions:
                return False, "檔案類型不支援", None
            
            return True, "", safe_path
            
        except Exception as e:
            return False, f"檔案路徑驗證失敗: {str(e)}", None
    
    @staticmethod
    def validate_summary_file(filename: str, summary_folder: Path) -> Tuple[bool, str, Optional[Path]]:
        """驗證摘要檔案"""
        return FileValidator.validate_safe_path(
            filename, 
            summary_folder, 
            allowed_extensions={'.txt'}
        )
    
    @staticmethod
    def validate_subtitle_file(filename: str, subtitle_folder: Path) -> Tuple[bool, str, Optional[Path]]:
        """驗證字幕檔案"""
        # 處理檔案名稱轉換（.txt -> .srt）
        if filename.endswith('.txt'):
            filename = filename[:-4] + '.srt'
        elif not filename.endswith('.srt'):
            filename += '.srt'
            
        return FileValidator.validate_safe_path(
            filename, 
            subtitle_folder, 
            allowed_extensions={'.srt'}
        )
    
    @staticmethod
    def validate_upload_file(file_size: int, file_extension: str, 
                           max_size: int, allowed_extensions: set) -> Tuple[bool, str]:
        """
        驗證上傳檔案
        
        Args:
            file_size: 檔案大小（位元組）
            file_extension: 檔案副檔名
            max_size: 最大檔案大小
            allowed_extensions: 允許的副檔名集合
        
        Returns:
            tuple: (是否有效, 錯誤訊息)
        """
        # 檢查檔案大小
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            return False, f'檔案過大，最大限制 {max_mb:.0f}MB，目前檔案 {size_mb:.1f}MB'
        
        # 檢查檔案類型
        if file_extension.lower() not in allowed_extensions:
            return False, f'不支援的檔案格式：{file_extension}。支援格式：{", ".join(sorted(allowed_extensions))}'
        
        return True, ""