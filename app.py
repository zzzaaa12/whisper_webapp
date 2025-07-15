import os
import sys
import threading
import traceback
from pathlib import Path
from datetime import datetime
import re
import shutil
import time
import json
import uuid

from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_socketio import emit
from dotenv import load_dotenv
import requests



from src.services.auth_service import AuthService
from src.services.socketio_instance import init_socketio
from task_queue import get_task_queue, TaskStatus

from src.utils.file_sanitizer import sanitize_filename as utils_sanitize_filename
from src.utils.srt_converter import segments_to_srt as utils_segments_to_srt
from src.utils.time_formatter import get_timestamp as utils_get_timestamp
from src.services.notification_service import send_telegram_notification as utils_send_telegram_notification
from src.services.whisper_manager import get_whisper_manager, transcribe_audio

from src.services.file_service import FileService
from src.services.bookmark_service import BookmarkService
from src.services.trash_service import TrashService
from src.services.url_service import URLService
from src.utils.path_manager import get_path_manager
from src.utils.url_builder import URLBuilder
from src.utils.logger_manager import setup_logging, get_logger_manager
from src.services.log_service import LogService
from src.services.gpu_service import GPUService
from src.services.socket_service import SocketService

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
BASE_DIR = Path(__file__).parent.resolve()
from src.config import init_config, get_config
init_config(BASE_DIR)

# 初始化日誌系統
setup_logging(BASE_DIR / "logs", enable_console=True)
logger_manager = get_logger_manager()

# 確保路徑管理器在配置初始化後才被使用
path_manager = get_path_manager()

app.config['SECRET_KEY'] = get_config('SECRET_KEY', os.urandom(24))

@app.context_processor
def inject_session():
    """Make session available to all templates"""
    return dict(session=session)

@app.context_processor
def inject_config():
    """Make config available to all templates"""
    return dict(config=get_config)

socketio = init_socketio(app)
auth_service = AuthService()

DOWNLOAD_FOLDER = get_config('PATHS.DOWNLOADS_DIR')
SUMMARY_FOLDER = get_config('PATHS.SUMMARIES_DIR')
SUBTITLE_FOLDER = get_config('PATHS.SUBTITLES_DIR')
LOG_FOLDER = get_config('PATHS.LOGS_DIR')
TRASH_FOLDER = get_config('PATHS.TRASH_DIR')
UPLOAD_FOLDER = get_config('PATHS.UPLOADS_DIR')

file_service = FileService()
log_service = LogService(get_config('PATHS.LOGS_DIR'))
gpu_service = GPUService()
socket_service = SocketService(socketio, log_service)
bookmark_service = BookmarkService(BASE_DIR / "bookmarks.json", get_config('PATHS.SUMMARIES_DIR'))
trash_service = TrashService(get_config('PATHS.TRASH_DIR'), get_config('PATHS.SUMMARIES_DIR'), get_config('PATHS.SUBTITLES_DIR'))
url_service = URLService()


# 安全性增強：設定安全標頭
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # 如果使用 SSL，設定更強的 HSTS
    use_ssl = get_config("USE_SSL", False)
    if use_ssl:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    else:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response

@app.before_request
def require_access_code():
    """在每個請求前檢查是否需要通行碼"""
    # API 請求應跳過此驗證
    if request.path.startswith('/api'):
        return

    # 檢查功能是否開啟
    if not get_config("ACCESS_CODE_ALL_PAGE", False):
        return

    # 檢查使用者是否已通過驗證
    if session.get('is_authorized'):
        return

    # 允許訪問特定頁面，避免無限重導向
    # 也允許訪問 Socket.IO 的內部路徑
    if request.endpoint in ['main.access', 'static'] or request.path.startswith('/socket.io'):
        return

    # 重導向到通行碼輸入頁面
    return redirect(url_for('main.access', next=request.path))

# --- Global Definitions ---




SERVER_STATE = {'is_busy': False, 'current_task': '無'}
state_lock = threading.Lock()

# 新增取消任務追蹤
current_task_sid = None
task_lock = threading.Lock()

# --- Log Persistence ---





#延遲導入，在需要時才載入


# --- Bookmark Management ---


# 移除重複的模型變數，統一使用背景工作程序的模型
# model = None  # 移除這行


# 新增 GPU 狀態追蹤






# (folders are now defined inside the worker)


def log_and_emit(message, level='info', sid=None):
    """Helper function to print to console and emit to client."""
    logger_manager.info(f"[{level.upper()}] {message}", "app")

    # 儲存日誌到檔案
    if sid:
        log_service.save_log_entry(sid, message, level)

    socketio.emit('update_log', {'log': message, 'type': level}, to=sid)

def update_server_state(is_busy, task_description):
    """Updates and broadcasts the server's state."""
    with state_lock:
        SERVER_STATE['is_busy'] = is_busy
        SERVER_STATE['current_task'] = task_description
        socketio.emit('server_status_update', SERVER_STATE)
    logger_manager.info(f"Server state updated: {SERVER_STATE}", "app")

# sanitize_filename 函數已移至 utils.py

# whisper_segments_to_srt 函數已移至 utils.py (統一為 segments_to_srt)








# _actual_transcribe_task 函數已移除，所有語音辨識由 worker process 處理

# do_transcribe 函數已移除，所有語音辨識由 worker process 處理

# 新增統一的任務入列函數






from src.routes.main import main_bp
from src.routes.api import api_bp

app.register_blueprint(main_bp)
app.register_blueprint(api_bp)


@socketio.on('connect')
def handle_connect():
    sid = request.sid
    logger_manager.info(f"Client connected: {sid}", "socketio")

    previous_logs = log_service.get_session_logs(sid)
    if previous_logs.strip():
        for line in previous_logs.strip().split('\n'):
            if line.strip():
                socket_service.log_and_emit(line.strip(), 'info', sid)

    socket_service.emit_server_status_update(SERVER_STATE['is_busy'], SERVER_STATE['current_task'])

    gpu_status = gpu_service.get_gpu_status()
    socket_service.emit_gpu_status_update(gpu_status, sid)

    socket_service.log_and_emit('成功連接至後端伺服器。', 'success', sid)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    logger_manager.info(f"Client disconnected: {sid}", "socketio")

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
    sid = request.sid
    client_ip = auth_service.get_client_ip()

    if not (isinstance(data, dict) and data.get('audio_url') and data.get('access_code') is not None):
        return socket_service.log_and_emit("🔴 錯誤：請求格式不正確。", 'error', sid)

    if auth_service.is_ip_blocked(client_ip):
        remaining_time = auth_service.get_block_remaining_time(client_ip)
        minutes = remaining_time // 60
        seconds = remaining_time % 60
        return socket_service.log_and_emit(f"🔒 您的 IP 已被暫時封鎖，請等待 {minutes} 分 {seconds} 秒後再試。", 'error', sid)

    if not auth_service.verify_access_code(data.get('access_code')):
        auth_service.record_failed_attempt(client_ip)
        remaining_attempts = auth_service.get_remaining_attempts(client_ip)

        if remaining_attempts > 0:
            socket_service.log_and_emit(f"🔴 錯誤：通行碼不正確。剩餘嘗試次數：{remaining_attempts}", 'error', sid)
        else:
            socket_service.log_and_emit(f"🔒 錯誤：通行碼不正確。您的 IP 已被封鎖 {auth_service.block_duration//60} 分鐘。", 'error', sid)

        socket_service.emit_access_code_error(sid)
        return

    auth_service.record_successful_attempt(client_ip)

    try:
        url = data.get('audio_url')
        socket_service.log_and_emit(f"收到請求，準備處理網址: {url}", 'info', sid)

        task_id = get_task_queue().add_task(
            task_type='youtube',
            data={'url': url},
            user_ip=client_ip,
            priority=5
        )

        queue_position = get_task_queue().get_user_queue_position(task_id)

        website_base_url = get_config("WEBSITE_BASE_URL", "127.0.0.1")
        use_ssl = get_config("USE_SSL", False)
        server_port = get_config("SERVER_PORT", 5000)
        public_port = get_config("PUBLIC_PORT", 0)

        effective_port = public_port if public_port > 0 else server_port

        protocol = "https" if use_ssl else "http"
        if (protocol == "http" and effective_port == 80) or \
           (protocol == "https" and effective_port == 443):
            # Standard ports, no need to include port in URL
            base_url = f"{protocol}://{website_base_url}"
        else:
            base_url = f"{protocol}://{website_base_url}:{effective_port}"
        summary_url = f"{base_url}/summaries/{task_id}"

        if queue_position > 1:
            socket_service.log_and_emit(f"⏳ 任務已加入佇列，目前排隊位置：第 {queue_position} 位，任務ID：{task_id[:8]}。預計摘要網址：{summary_url}", 'warning', sid)
        else:
            socket_service.log_and_emit(f'✅ 任務已接收並開始處理，任務ID：{task_id[:8]}。預計摘要網址：{summary_url}', 'success', sid)

    except Exception as e:
        socket_service.log_and_emit(f"❌ 加入佇列失敗：{str(e)}", 'error', sid)



@socketio.on('cancel_processing')
def handle_cancel_processing():
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






























@app.route('/admin/login-attempts')
def admin_login_attempts():
    """管理端點：查看登入嘗試狀態"""
    admin_code = get_config("ADMIN_CODE")
    if not admin_code or request.args.get('code') != admin_code:
        return "未授權訪問", 401

    attempts_info = auth_service.get_login_attempts_info()
    return render_template('admin_login_attempts.html', attempts=attempts_info, max_attempts=auth_service.max_attempts, block_duration=auth_service.block_duration//60)



@socketio.on('request_gpu_status')
def handle_request_gpu_status():
    """處理客戶端請求 GPU 狀態"""
    sid = request.sid
    status = gpu_service.get_gpu_status()
    socket_service.emit_gpu_status_update(status, sid)

















































# --- Main Execution ---
if __name__ == '__main__':
    # 檢查系統配置並顯示警告
    access_code = get_config("ACCESS_CODE")
    openai_key = get_config("OPENAI_API_KEY")

    logger_manager.info("🔍 檢查系統配置...", "app")

    if not access_code:
        logger_manager.warning("未設定 ACCESS_CODE 環境變數", "app")
        logger_manager.warning("系統將允許無通行碼存取，建議設定 ACCESS_CODE 以提升安全性", "app")
    else:
        logger_manager.info("✅ ACCESS_CODE 已設定", "app")

    if not openai_key:
        logger_manager.warning("未設定 OPENAI_API_KEY", "app")
        logger_manager.warning("AI 摘要功能將無法使用，請設定 OPENAI_API_KEY 啟用此功能", "app")
    else:
        logger_manager.info("✅ OPENAI_API_KEY 已設定", "app")

    # 檢查 SSL 配置
    use_ssl = get_config("USE_SSL", False)
    ssl_context = None
    server_port = int(get_config("SERVER_PORT", 5000))  # 確保是整數類型

    if use_ssl:
        cert_file = get_config('PATHS.CERTS_DIR') / 'cert.pem'
        key_file = get_config('PATHS.CERTS_DIR') / 'key.pem'

        if cert_file.exists() and key_file.exists():
            try:
                import ssl
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(cert_file, key_file)
                logger_manager.info("✅ SSL 憑證已載入，將使用 HTTPS 模式", "app")
                logger_manager.info(f"🔐 HTTPS 伺服器將在 https://0.0.0.0:{server_port} 啟動", "app")
            except Exception as e:
                logger_manager.warning(f"SSL 憑證載入失敗: {e}", "app")
                logger_manager.warning("將使用 HTTP 模式啟動", "app")
                ssl_context = None
        else:
            logger_manager.warning("找不到 SSL 憑證檔案 (certs/cert.pem, certs/key.pem)", "app")
            logger_manager.warning("將使用 HTTP 模式啟動", "app")
    else:
        logger_manager.info("📡 使用 HTTP 模式", "app")

    logger_manager.info("🚀 繼續啟動系統...", "app")

    for folder_key in ['DOWNLOADS_DIR', 'SUMMARIES_DIR', 'SUBTITLES_DIR', 'LOGS_DIR', 'TRASH_DIR', 'UPLOADS_DIR']:
        file_service.ensure_dir(get_config(f'PATHS.{folder_key}'))

    # 建立回收桶子資料夾
    file_service.ensure_dir(get_config('PATHS.TRASH_DIR') / "summaries")
    file_service.ensure_dir(get_config('PATHS.TRASH_DIR') / "subtitles")

    # 啟動新的佇列工作程式（與舊系統並行）
    try:
        from src.services.queue_worker import start_queue_worker
        queue_worker = start_queue_worker(
            data_dir=BASE_DIR,
            openai_key=get_config("OPENAI_API_KEY")
        )
        logger_manager.info("✅ 新任務佇列工作程式已啟動", "app")
    except Exception as e:
        logger_manager.warning(f"新任務佇列工作程式啟動失敗: {e}", "app")



    # 顯示啟動訊息
    if ssl_context:
        logger_manager.info(f"🔐 HTTPS 伺服器啟動，請在瀏覽器中開啟 https://127.0.0.1:{server_port}", "app")
        logger_manager.info(f"或透過網路存取：https://你的IP地址:{server_port}", "app")
    else:
        logger_manager.info(f"📡 HTTP 伺服器啟動，請在瀏覽器中開啟 http://127.0.0.1:{server_port}", "app")
        logger_manager.info(f"或透過網路存取：http://你的IP地址:{server_port}", "app")

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=server_port,
            use_reloader=False,
            ssl_context=ssl_context
        )
    finally:
        logger_manager.info("主伺服器準備關閉...", "app")
        # 停止新的佇列工作程式
        try:
            from src.services.queue_worker import stop_queue_worker
            stop_queue_worker()
            logger_manager.info("✅ 新任務佇列工作程式已停止", "app")
        except Exception as e:
            logger_manager.warning(f"停止新任務佇列工作程式失敗: {e}", "app")
        logger_manager.info("程式已完全關閉。", "app")
