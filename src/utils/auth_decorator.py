"""
統一認證裝飾器
解決通行碼驗證重複問題
"""

from functools import wraps
from flask import request
from src.services.auth_service import AuthService
from src.utils.api_response import APIResponse

# 全域認證服務實例
auth_service = AuthService()


def require_access_code(f):
    """
    需要通行碼驗證的裝飾器
    
    使用方式:
    @require_access_code
    def my_api_function():
        pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 從請求中獲取通行碼
        access_code = None
        
        if request.is_json:
            data = request.get_json()
            access_code = data.get('access_code') if data else None
        else:
            access_code = request.form.get('access_code')
        
        # 驗證通行碼
        if not auth_service.verify_access_code(access_code):
            return APIResponse.auth_error()
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_access_code_legacy(f):
    """
    需要通行碼驗證的裝飾器（舊版API格式）
    
    使用方式:
    @require_access_code_legacy
    def my_youtube_api_function():
        pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 從請求中獲取通行碼
        access_code = None
        
        if request.is_json:
            data = request.get_json()
            access_code = data.get('access_code') if data else None
        else:
            access_code = request.form.get('access_code')
        
        # 驗證通行碼
        if not auth_service.verify_access_code(access_code):
            from src.utils.api_response import LegacyAPIResponse
            return LegacyAPIResponse.error("通行碼錯誤", 401)
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_auth_service() -> AuthService:
    """獲取認證服務實例"""
    return auth_service