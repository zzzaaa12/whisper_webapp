
import re

class URLService:
    """URL 處理服務"""

    @staticmethod
    def detect_url_type(url: str) -> str:
        """檢測 URL 類型並返回相應的處理器"""
        url_lower = url.lower()
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        return 'unknown'

    @staticmethod
    def validate_youtube_url(url: str) -> bool:
        """驗證 YouTube URL 格式是否正確"""
        youtube_pattern = r'^https?://(www\.)?(youtube\.com|youtu\.be)/.+'
        return bool(re.match(youtube_pattern, url, re.IGNORECASE))
