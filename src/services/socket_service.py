
from flask_socketio import SocketIO
from typing import Optional

from src.services.log_service import LogService

class SocketService:
    """SocketIO 服務，負責發送訊息和日誌"""

    def __init__(self, socketio: SocketIO, log_service: LogService):
        self.socketio = socketio
        self.log_service = log_service

    def log_and_emit(self, message: str, level: str = 'info', sid: Optional[str] = None):
        """Helper function to print to console and emit to client."""
        print(f"[{level.upper()}] {message}")

        if sid:
            self.log_service.save_log_entry(sid, message, level)

        self.socketio.emit('update_log', {'log': message, 'type': level}, to=sid)

    def emit_server_status_update(self, is_busy: bool, current_task: str):
        """Updates and broadcasts the server's state."""
        self.socketio.emit('server_status_update', {'is_busy': is_busy, 'current_task': current_task})
        print(f"Server state updated: {{ 'is_busy': {is_busy}, 'current_task': '{current_task}' }}")

    def emit_gpu_status_update(self, status: dict, sid: Optional[str] = None):
        """更新 GPU 狀態並廣播給所有客戶端"""
        self.socketio.emit('gpu_status_update', status, to=sid)

    def emit_processing_finished(self, sid: Optional[str] = None):
        """發送處理完成事件"""
        self.socketio.emit('processing_finished', {}, to=sid)

    def emit_access_code_error(self, sid: Optional[str] = None):
        """發送通行碼錯誤事件"""
        self.socketio.emit('access_code_error', {'message': '通行碼錯誤'}, to=sid)
