"""
SocketIO 事件處理器
負責處理所有 SocketIO 相關的事件
"""

import threading
import time
from flask import request, session
from flask_socketio import emit

from src.config import get_config
from src.services.auth_service import AuthService
from src.core.task_queue import get_task_queue
from src.utils.logger_manager import get_logger_manager
from src.utils.url_builder import URLBuilder

# 全域狀態管理
SERVER_STATE = {'is_busy': False, 'current_task': '無'}
state_lock = threading.Lock()

# 任務追蹤
current_task_sid = None
task_lock = threading.Lock()


def register_socketio_handlers(socketio, services):
    """
    註冊所有 SocketIO 事件處理器

    Args:
        socketio: SocketIO 實例
        services: 服務實例字典
    """
    logger_manager = get_logger_manager()
    auth_service = services['auth_service']
    log_service = services['log_service']
    gpu_service = services['gpu_service']
    socket_service = services['socket_service']

    @socketio.on('connect')
    def handle_connect():
        """處理客戶端連接"""
        sid = request.sid
        logger_manager.info(f"Client connected: {sid}", "socketio")

        # 載入之前的日誌
        previous_logs = log_service.get_session_logs(sid)
        if previous_logs.strip():
            for line in previous_logs.strip().split('\n'):
                if line.strip():
                    socket_service.log_and_emit(line.strip(), 'info', sid)

        # 發送伺服器狀態
        socket_service.emit_server_status_update(
            SERVER_STATE['is_busy'],
            SERVER_STATE['current_task']
        )

        # 發送 GPU 狀態
        gpu_status = gpu_service.get_gpu_status()
        socket_service.emit_gpu_status_update(gpu_status, sid)

        socket_service.log_and_emit('成功連接至後端伺服器。', 'success', sid)

    @socketio.on('disconnect')
    def handle_disconnect():
        """處理客戶端斷線"""
        sid = request.sid
        logger_manager.info(f"Client disconnected: {sid}", "socketio")

        # 延遲清理日誌
        def delayed_cleanup():
            time.sleep(30)
            log_service.clear_session_logs(sid)

        threading.Thread(target=delayed_cleanup, daemon=True).start()

    @socketio.on('clear_logs')
    def handle_clear_logs():
        """處理清除日誌請求"""
        sid = request.sid
        log_service.clear_session_logs(sid)
        socket_service.log_and_emit('日誌記錄已清除', 'info', sid)

    @socketio.on('start_processing')
    def handle_start_processing(data):
        """處理開始處理請求"""
        sid = request.sid
        client_ip = auth_service.get_client_ip()

        # 驗證請求格式
        if not (isinstance(data, dict) and data.get('audio_url') and data.get('access_code') is not None):
            return socket_service.log_and_emit("🔴 錯誤：請求格式不正確。", 'error', sid)

        # 檢查 IP 是否被封鎖
        if auth_service.is_ip_blocked(client_ip):
            remaining_time = auth_service.get_block_remaining_time(client_ip)
            minutes = remaining_time // 60
            seconds = remaining_time % 60
            return socket_service.log_and_emit(
                f"🔒 您的 IP 已被暫時封鎖，請等待 {minutes} 分 {seconds} 秒後再試。",
                'error', sid
            )

        # 檢查通行碼
        if not _verify_access_code(data, auth_service, socket_service, sid, client_ip):
            return

        # 處理任務
        try:
            url = data.get('audio_url')
            socket_service.log_and_emit(f"收到請求，準備處理網址: {url}", 'info', sid)

            # 加入任務佇列
            task_id = get_task_queue().add_task(
                task_type='youtube',
                data={'url': url},
                user_ip=client_ip,
                priority=5
            )

            queue_position = get_task_queue().get_user_queue_position(task_id)

            # 構建摘要 URL
            base_url = URLBuilder.build_base_url()
            summary_url = f"{base_url}/summaries/{task_id}"

            # 發送回應
            if queue_position > 1:
                socket_service.log_and_emit(
                    f"⏳ 任務已加入佇列，目前排隊位置：第 {queue_position} 位，任務ID：{task_id[:8]}。預計摘要網址：{summary_url}",
                    'warning', sid
                )
            else:
                socket_service.log_and_emit(
                    f'✅ 任務已接收並開始處理，任務ID：{task_id[:8]}。預計摘要網址：{summary_url}',
                    'success', sid
                )

        except Exception as e:
            socket_service.log_and_emit(f"❌ 加入佇列失敗：{str(e)}", 'error', sid)

    @socketio.on('cancel_processing')
    def handle_cancel_processing():
        """處理取消處理請求"""
        sid = request.sid
        global current_task_sid

        with task_lock:
            if current_task_sid == sid:
                current_task_sid = None
                socket_service.log_and_emit("🛑 任務已取消", 'info', sid)
                socket_service.emit_server_status_update(False, "空閒")
                socket_service.emit_processing_finished(sid)
            else:
                socket_service.log_and_emit("❌ 沒有可取消的任務", 'error', sid)

    @socketio.on('request_gpu_status')
    def handle_request_gpu_status():
        """處理客戶端請求 GPU 狀態"""
        sid = request.sid
        status = gpu_service.get_gpu_status()
        socket_service.emit_gpu_status_update(status, sid)


def _verify_access_code(data, auth_service, socket_service, sid, client_ip):
    """
    驗證通行碼

    Args:
        data: 請求資料
        auth_service: 認證服務
        socket_service: Socket 服務
        sid: Session ID
        client_ip: 客戶端 IP

    Returns:
        bool: 驗證是否成功
    """
    # 檢查是否需要通行碼驗證
    if get_config("ACCESS_CODE_ALL_PAGE", False) and session.get('is_authorized'):
        # 已通過全站認證，跳過通行碼驗證
        return True

    # 需要驗證通行碼
    if not auth_service.verify_access_code(data.get('access_code')):
        auth_service.record_failed_attempt(client_ip)
        remaining_attempts = auth_service.get_remaining_attempts(client_ip)

        if remaining_attempts > 0:
            socket_service.log_and_emit(
                f"🔴 錯誤：通行碼不正確。剩餘嘗試次數：{remaining_attempts}",
                'error', sid
            )
        else:
            socket_service.log_and_emit(
                f"🔒 錯誤：通行碼不正確。您的 IP 已被封鎖 {auth_service.block_duration//60} 分鐘。",
                'error', sid
            )

        socket_service.emit_access_code_error(sid)
        return False

    auth_service.record_successful_attempt(client_ip)
    return True


def log_and_emit(socketio, message, level='info', sid=None):
    """
    輔助函數：記錄日誌並發送到客戶端

    Args:
        socketio: SocketIO 實例
        message: 訊息內容
        level: 日誌等級
        sid: Session ID
    """
    logger_manager = get_logger_manager()
    logger_manager.info(f"[{level.upper()}] {message}", "app")

    socketio.emit('update_log', {'log': message, 'type': level}, to=sid)


def update_server_state(socketio, is_busy, task_description):
    """
    更新並廣播伺服器狀態

    Args:
        socketio: SocketIO 實例
        is_busy: 是否忙碌
        task_description: 任務描述
    """
    global SERVER_STATE

    with state_lock:
        SERVER_STATE['is_busy'] = is_busy
        SERVER_STATE['current_task'] = task_description
        socketio.emit('server_status_update', SERVER_STATE)

    logger_manager = get_logger_manager()
    logger_manager.info(f"Server state updated: {SERVER_STATE}", "app")


def get_server_state():
    """
    獲取當前伺服器狀態

    Returns:
        dict: 伺服器狀態
    """
    with state_lock:
        return SERVER_STATE.copy()