"""
統一錯誤處理中介軟體
提供全域的錯誤處理和日誌記錄
"""

import traceback
from flask import request, current_app
from werkzeug.exceptions import HTTPException

from src.utils.api_response import APIResponse
from src.utils.logger_manager import get_logger_manager


def register_error_handlers(app):
    """
    註冊全域錯誤處理器

    Args:
        app: Flask 應用程式實例
    """
    logger_manager = get_logger_manager()

    @app.errorhandler(400)
    def handle_bad_request(error):
        """處理 400 錯誤"""
        logger_manager.warning(f"Bad Request: {error.description}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.validation_error(error.description or "請求格式錯誤")

        return error

    @app.errorhandler(401)
    def handle_unauthorized(error):
        """處理 401 錯誤"""
        logger_manager.warning(f"Unauthorized: {error.description}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.auth_error(error.description or "未授權訪問")

        return error

    @app.errorhandler(403)
    def handle_forbidden(error):
        """處理 403 錯誤"""
        logger_manager.warning(f"Forbidden: {error.description}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.auth_error(error.description or "禁止訪問")

        return error

    @app.errorhandler(404)
    def handle_not_found(error):
        """處理 404 錯誤"""
        logger_manager.info(f"Not Found: {request.path}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.not_found("請求的資源不存在")

        return error

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """處理 405 錯誤"""
        logger_manager.warning(f"Method Not Allowed: {request.method} {request.path}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.validation_error(f"不支援的請求方法: {request.method}")

        return error

    @app.errorhandler(413)
    def handle_payload_too_large(error):
        """處理 413 錯誤"""
        logger_manager.warning(f"Payload Too Large: {request.path}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.payload_too_large("請求內容過大")

        return error

    @app.errorhandler(429)
    def handle_too_many_requests(error):
        """處理 429 錯誤"""
        logger_manager.warning(f"Too Many Requests: {request.path}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.error("請求過於頻繁，請稍後再試", 429)

        return error

    @app.errorhandler(500)
    def handle_internal_error(error):
        """處理 500 錯誤"""
        logger_manager.error(f"Internal Server Error: {error}", "error_handler")
        logger_manager.error(f"Traceback: {traceback.format_exc()}", "error_handler")

        if request.path.startswith('/api/'):
            return APIResponse.internal_error("內部伺服器錯誤")

        return error

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """處理未預期的錯誤"""
        logger_manager.error(f"Unexpected Error: {error}", "error_handler")
        logger_manager.error(f"Traceback: {traceback.format_exc()}", "error_handler")

        # 如果是 HTTP 異常，讓其他處理器處理
        if isinstance(error, HTTPException):
            return error

        if request.path.startswith('/api/'):
            return APIResponse.internal_error("發生未預期的錯誤")

        # 對於非 API 請求，返回 500 錯誤
        return "內部伺服器錯誤", 500


def log_request_info():
    """記錄請求資訊（用於除錯）"""
    logger_manager = get_logger_manager()

    if current_app.debug:
        logger_manager.debug(
            f"Request: {request.method} {request.path} "
            f"from {request.remote_addr}",
            "request_logger"
        )


def register_request_logging(app):
    """
    註冊請求日誌記錄

    Args:
        app: Flask 應用程式實例
    """
    @app.before_request
    def log_request():
        """記錄請求開始"""
        if app.debug:
            log_request_info()

    @app.after_request
    def log_response(response):
        """記錄回應"""
        if app.debug:
            logger_manager = get_logger_manager()
            logger_manager.debug(
                f"Response: {response.status_code} for {request.method} {request.path}",
                "request_logger"
            )
        return response