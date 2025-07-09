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

from flask import Flask, render_template, request, jsonify, send_file
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
from src.services.log_service import LogService
from src.services.gpu_service import GPUService
from src.services.socket_service import SocketService

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
BASE_DIR = Path(__file__).parent.resolve()
from src.config import init_config, get_config
init_config(BASE_DIR)


app.config['SECRET_KEY'] = get_config('SECRET_KEY', os.urandom(24))
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
    print(f"[{level.upper()}] {message}")

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
    print(f"Server state updated: {SERVER_STATE}")

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
    sid = request.sid; print(f"Client connected: {sid}")

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
    print(f"Client disconnected: {sid}")

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

        if queue_position > 1:
            socket_service.log_and_emit(f"⏳ 任務已加入佇列，目前排隊位置：第 {queue_position} 位，任務ID：{task_id[:8]}", 'warning', sid)
        else:
            socket_service.log_and_emit(f'✅ 任務已接收並開始處理，任務ID：{task_id[:8]}', 'success', sid)

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

    print("🔍 檢查系統配置...")

    if not access_code:
        print("⚠️  警告：未設定 ACCESS_CODE 環境變數")
        print("   系統將允許無通行碼存取，建議設定 ACCESS_CODE 以提升安全性")
    else:
        print("✅ ACCESS_CODE 已設定")

    if not openai_key:
        print("⚠️  警告：未設定 OPENAI_API_KEY")
        print("   AI 摘要功能將無法使用，請設定 OPENAI_API_KEY 啟用此功能")
    else:
        print("✅ OPENAI_API_KEY 已設定")

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
                print("✅ SSL 憑證已載入，將使用 HTTPS 模式")
                print(f"🔐 HTTPS 伺服器將在 https://0.0.0.0:{server_port} 啟動")
            except Exception as e:
                print(f"⚠️  SSL 憑證載入失敗: {e}")
                print("   將使用 HTTP 模式啟動")
                ssl_context = None
        else:
            print("⚠️  找不到 SSL 憑證檔案 (certs/cert.pem, certs/key.pem)")
            print("   將使用 HTTP 模式啟動")
    else:
        print("📡 使用 HTTP 模式")

    print("🚀 繼續啟動系統...")

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
        print("✅ 新任務佇列工作程式已啟動")
    except Exception as e:
        print(f"⚠️  新任務佇列工作程式啟動失敗: {e}")

    

    # 顯示啟動訊息
    if ssl_context:
        print(f"🔐 HTTPS 伺服器啟動，請在瀏覽器中開啟 https://127.0.0.1:{server_port}")
        print(f"   或透過網路存取：https://你的IP地址:{server_port}")
    else:
        print(f"📡 HTTP 伺服器啟動，請在瀏覽器中開啟 http://127.0.0.1:{server_port}")
        print(f"   或透過網路存取：http://你的IP地址:{server_port}")

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=server_port,
            use_reloader=False,
            ssl_context=ssl_context
        )
    finally:
        print("主伺服器準備關閉...")
        # 停止新的佇列工作程式
        try:
            from queue_worker import stop_queue_worker
            stop_queue_worker()
            print("✅ 新任務佇列工作程式已停止")
        except Exception as e:
            print(f"⚠️  停止新任務佇列工作程式失敗: {e}")
        print("程式已完全關閉。")
