

import re
from src.utils.traditional_converter import to_traditional

class FileNameSanitizer:
    """統一檔案名清理器"""

    @staticmethod
    def sanitize(filename: str, max_length: int = 80) -> str:
        """統一檔案名清理函數"""
        if not filename:
            return "unknown"

        original = filename

        # 0. 轉換為繁體中文
        filename = to_traditional(filename)

        # 1. 移除 Windows 禁用字元
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

        # 2. 移除常見特殊符號（但保留中文、數字、字母）
        filename = re.sub(r'[\[\]{}()!@#$%^&+=~`]', '_', filename)

        # 3. 移除表情符號和其他 Unicode 符號（保留中文字元）
        filename = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf\w\s\-._]', '_', filename, flags=re.UNICODE)

        # 4. 處理多重空格和底線
        filename = re.sub(r'\s+', '_', filename)
        filename = re.sub(r'_+', '_', filename)

        # 5. 移除開頭和結尾的特殊字元
        filename = filename.strip('._')

        # 6. 長度處理（考慮中文字元）
        if len(filename.encode('utf-8')) > max_length * 2:
            if max_length > 20:
                # 智能截斷：保留前 60% 和後面部分
                keep_start = int(max_length * 0.6)
                keep_end = max_length - keep_start - 3

                safe_start = filename[:keep_start].encode('utf-8')[:keep_start*2].decode('utf-8', errors='ignore')
                safe_end = filename[-keep_end:].encode('utf-8')[-keep_end*2:].decode('utf-8', errors='ignore') if keep_end > 0 else ""

                filename = safe_start + "..." + safe_end
            else:
                filename = filename.encode('utf-8')[:max_length].decode('utf-8', errors='ignore')

        if '_-_' in filename:
            filename = filename.replace('_-_', ' - ')

        result = filename if filename else "unknown"
        return result

# 便捷函數導出
def sanitize_filename(filename: str, max_length: int = 80) -> str:
    """便捷檔案名清理函數"""
    return FileNameSanitizer.sanitize(filename, max_length)

