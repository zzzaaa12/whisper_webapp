"""
統一URL構建工具
解決URL構建邏輯重複問題
"""

from src.config import get_config


class URLBuilder:
    """URL構建工具類"""
    
    @staticmethod
    def build_base_url() -> str:
        """
        構建基礎URL
        
        Returns:
            str: 完整的基礎URL
        """
        website_base_url = get_config("WEBSITE_BASE_URL", "127.0.0.1")
        use_ssl = get_config("USE_SSL", False)
        server_port = get_config("SERVER_PORT", 5000)
        public_port = get_config("PUBLIC_PORT", 0)
        
        # 決定有效埠號
        effective_port = public_port if public_port > 0 else server_port
        
        # 決定協議
        protocol = "https" if use_ssl else "http"
        
        # 標準埠號不需要在URL中顯示
        if (protocol == "http" and effective_port == 80) or \
           (protocol == "https" and effective_port == 443):
            return f"{protocol}://{website_base_url}"
        else:
            return f"{protocol}://{website_base_url}:{effective_port}"
    
    @staticmethod
    def build_summary_url(task_id: str) -> str:
        """
        構建摘要頁面URL
        
        Args:
            task_id: 任務ID
        
        Returns:
            str: 完整的摘要URL
        """
        base_url = URLBuilder.build_base_url()
        return f"{base_url}/summary?task_id={task_id}"
    
    @staticmethod
    def build_queue_url() -> str:
        """
        構建佇列頁面URL
        
        Returns:
            str: 完整的佇列URL
        """
        base_url = URLBuilder.build_base_url()
        return f"{base_url}/queue"