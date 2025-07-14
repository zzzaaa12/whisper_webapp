"""
統一API回應工具
解決API回應格式重複問題
"""

from flask import jsonify
from typing import Any, Dict, Optional


class APIResponse:
    """統一的API回應工具類"""
    
    @staticmethod
    def success(data: Optional[Dict[str, Any]] = None, message: str = "操作成功", status_code: int = 200):
        """
        成功回應
        
        Args:
            data: 回應資料
            message: 成功訊息
            status_code: HTTP狀態碼
        
        Returns:
            Flask Response
        """
        response = {
            'success': True,
            'message': message
        }
        
        if data:
            response.update(data)
        
        return jsonify(response), status_code
    
    @staticmethod
    def error(message: str, status_code: int = 500, error_code: Optional[str] = None):
        """
        錯誤回應
        
        Args:
            message: 錯誤訊息
            status_code: HTTP狀態碼
            error_code: 錯誤代碼（可選）
        
        Returns:
            Flask Response
        """
        response = {
            'success': False,
            'message': message
        }
        
        if error_code:
            response['error_code'] = error_code
        
        return jsonify(response), status_code
    
    @staticmethod
    def validation_error(message: str):
        """驗證錯誤回應"""
        return APIResponse.error(message, 400, 'VALIDATION_ERROR')
    
    @staticmethod
    def auth_error(message: str = "通行碼錯誤"):
        """認證錯誤回應"""
        return APIResponse.error(message, 401, 'AUTH_ERROR')
    
    @staticmethod
    def not_found(message: str = "資源未找到"):
        """未找到錯誤回應"""
        return APIResponse.error(message, 404, 'NOT_FOUND')
    
    @staticmethod
    def conflict(message: str):
        """衝突錯誤回應"""
        return APIResponse.error(message, 409, 'CONFLICT')
    
    @staticmethod
    def payload_too_large(message: str):
        """檔案過大錯誤回應"""
        return APIResponse.error(message, 413, 'PAYLOAD_TOO_LARGE')
    
    @staticmethod
    def internal_error(message: str = "內部伺服器錯誤"):
        """內部錯誤回應"""
        return APIResponse.error(message, 500, 'INTERNAL_ERROR')


class LegacyAPIResponse:
    """舊版API回應格式（用於向後兼容）"""
    
    @staticmethod
    def processing(message: str, task_id: str, queue_position: int, **kwargs):
        """處理中回應（YouTube API格式）"""
        response = {
            'status': 'processing',
            'message': message,
            'task_id': task_id,
            'queue_position': queue_position
        }
        response.update(kwargs)
        return jsonify(response), 200
    
    @staticmethod
    def error(message: str, status_code: int = 500):
        """錯誤回應（YouTube API格式）"""
        return jsonify({
            'status': 'error',
            'message': message
        }), status_code