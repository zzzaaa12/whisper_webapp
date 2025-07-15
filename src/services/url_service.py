
import re
import yt_dlp

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

    @staticmethod
    def is_youtube_live(url: str) -> tuple[bool, str]:
        """
        檢測 YouTube URL 是否為 live 直播
        
        Returns:
            tuple: (is_live, message)
                - is_live: True 如果是直播，False 如果不是
                - message: 描述訊息
        """
        try:
            # 使用 yt-dlp 獲取影片資訊
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # 需要詳細資訊來檢測直播狀態
                'skip_download': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # 檢查是否為直播
                is_live = info.get('is_live', False)
                was_live = info.get('was_live', False)
                live_status = info.get('live_status', '')
                
                if is_live:
                    return True, "這是一個正在進行的直播"
                elif was_live:
                    return False, "這是一個已結束的直播錄影"
                elif live_status in ['is_live', 'is_upcoming']:
                    return True, f"這是一個直播 (狀態: {live_status})"
                else:
                    return False, "這是一般影片"
                    
        except Exception as e:
            # 如果無法獲取資訊，保守起見假設可能是直播
            return True, f"無法確定影片類型，為安全起見視為直播: {str(e)}"
