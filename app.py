import os
import sys
import threading
import traceback
from pathlib import Path
from datetime import datetime
import re
import shutil
import time
from multiprocessing import Process, Queue, Event
from queue import Empty as QueueEmpty
import json
import uuid

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import emit
from dotenv import load_dotenv
import requests

# 導入 SocketIO 實例管理
from socketio_instance import init_socketio

# 導入任務佇列系統
from task_queue import get_task_queue, TaskStatus

# 統一工具函數導入
from utils import (
    sanitize_filename as utils_sanitize_filename,
    segments_to_srt as utils_segments_to_srt,
    get_timestamp as utils_get_timestamp,
    send_telegram_notification as utils_send_telegram_notification,
    validate_access_code as utils_validate_access_code,
    file_ops
)
from whisper_manager import get_whisper_manager, transcribe_audio

# --- Initialization ---
# 讀取 config.json 設定檔
CONFIG = {}
config_path = Path(__file__).parent / 'config.json'
if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)

def get_config(key, default=None):
    # 先查 config.json，再查環境變數
    return CONFIG.get(key) or os.getenv(key) or default

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = get_config('SECRET_KEY', os.urandom(24))

# 初始化 SocketIO 實例
socketio = init_socketio(app)

# 初始化核心管理器
try:
    from app.core import FileOperationManager, SessionManager, SecurityManager
    file_manager = FileOperationManager(BASE_DIR)
    session_manager = SessionManager(LOG_FOLDER)
    security_manager = SecurityManager()
except ImportError:
    # 回退到原始實作
    print("Warning: Cannot import new core modules, using legacy implementation")
    file_manager = None
    session_manager = None
    security_manager = None

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
BASE_DIR = Path(__file__).parent.resolve()
DOWNLOAD_FOLDER = BASE_DIR / "downloads"
SUMMARY_FOLDER = BASE_DIR / "summaries"
SUBTITLE_FOLDER = BASE_DIR / "subtitles"
LOG_FOLDER = BASE_DIR / "logs"  # 新增日誌資料夾
TRASH_FOLDER = BASE_DIR / "trash"  # 新增回收桶資料夾
UPLOAD_FOLDER = BASE_DIR / "uploads"  # 新增上傳檔案資料夾
TRASH_METADATA_FILE = TRASH_FOLDER / "metadata.json"  # 回收桶記錄檔案
BOOKMARK_FILE = BASE_DIR / "bookmarks.json"  # 書籤檔案

task_queue = Queue()
results_queue = Queue()
stop_event = Event()

SERVER_STATE = {'is_busy': False, 'current_task': '無'}
state_lock = threading.Lock()

# 新增取消任務追蹤
current_task_sid = None
task_lock = threading.Lock()

# --- Log Persistence ---
def save_log_entry(sid, message, level='info'):
    """將日誌條目儲存到檔案"""
    if session_manager:
        session_manager.save_log_entry(sid, message, level)
    else:
        # 回退到原始實作
        try:
            log_file = LOG_FOLDER / f"session_{sid}.log"
            timestamp = utils_get_timestamp("log")
            log_entry = f"[{timestamp}] {message}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error saving log: {e}")

def get_session_logs(sid):
    """獲取指定 session 的日誌記錄"""
    if session_manager:
        return session_manager.get_session_logs(sid)
    else:
        # 回退到原始實作
        try:
            log_file = LOG_FOLDER / f"session_{sid}.log"
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"Error reading log: {e}")
            return ""

def clear_session_logs(sid):
    """清除指定 session 的日誌記錄"""
    if session_manager:
        session_manager.clear_session_logs(sid)
    else:
        # 回退到原始實作
        try:
            log_file = LOG_FOLDER / f"session_{sid}.log"
            if log_file.exists():
                log_file.unlink()
        except Exception as e:
            print(f"Error clearing log: {e}")

# --- Login Attempt Limiting ---
LOGIN_ATTEMPTS = {}  # {ip: {'count': int, 'first_attempt': timestamp, 'blocked_until': timestamp}}
MAX_ATTEMPTS = 5  # 最大嘗試次數
BLOCK_DURATION = 300  # 封鎖時間（秒）
attempts_lock = threading.Lock()

def get_client_ip():
    """獲取客戶端 IP 地址"""
    if security_manager:
        return security_manager.get_client_ip()
    else:
        # 回退到原始實作
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP') or ''
        else:
            return request.remote_addr or '127.0.0.1'

def is_ip_blocked(ip):
    """檢查 IP 是否被封鎖"""
    if security_manager:
        return security_manager.is_ip_blocked(ip)
    else:
        # 回退到原始實作
        with attempts_lock:
            if ip not in LOGIN_ATTEMPTS:
                return False

            attempt_data = LOGIN_ATTEMPTS[ip]
            current_time = time.time()

            # 檢查是否在封鎖期內
            if 'blocked_until' in attempt_data and current_time < attempt_data['blocked_until']:
                return True

            # 檢查是否超過重置時間（1小時）
            if current_time - attempt_data['first_attempt'] > 3600:
                # 重置嘗試次數
                del LOGIN_ATTEMPTS[ip]
                return False

            return False

def record_failed_attempt(ip):
    """記錄失敗的登入嘗試"""
    if security_manager:
        security_manager.record_failed_attempt(ip)
    else:
        # 回退到原始實作
        with attempts_lock:
            current_time = time.time()

            if ip not in LOGIN_ATTEMPTS:
                LOGIN_ATTEMPTS[ip] = {
                    'count': 1,
                    'first_attempt': current_time
                }
            else:
                LOGIN_ATTEMPTS[ip]['count'] += 1

                # 如果達到最大嘗試次數，設定封鎖時間
                if LOGIN_ATTEMPTS[ip]['count'] >= MAX_ATTEMPTS:
                    LOGIN_ATTEMPTS[ip]['blocked_until'] = current_time + BLOCK_DURATION

def record_successful_attempt(ip):
    """記錄成功的登入嘗試，重置計數器"""
    if security_manager:
        security_manager.record_successful_attempt(ip)
    else:
        # 回退到原始實作
        with attempts_lock:
            if ip in LOGIN_ATTEMPTS:
                del LOGIN_ATTEMPTS[ip]

def get_remaining_attempts(ip):
    """獲取剩餘嘗試次數"""
    if security_manager:
        return security_manager.get_remaining_attempts(ip)
    else:
        # 回退到原始實作
        with attempts_lock:
            if ip not in LOGIN_ATTEMPTS:
                return MAX_ATTEMPTS
            return max(0, MAX_ATTEMPTS - LOGIN_ATTEMPTS[ip]['count'])

def get_block_remaining_time(ip):
    """獲取封鎖剩餘時間（秒）"""
    if security_manager:
        return security_manager.get_block_remaining_time(ip)
    else:
        # 回退到原始實作
        with attempts_lock:
            if ip not in LOGIN_ATTEMPTS or 'blocked_until' not in LOGIN_ATTEMPTS[ip]:
                return 0
            return max(0, int(LOGIN_ATTEMPTS[ip]['blocked_until'] - time.time()))

# --- Global Variables & Model Loading ---
#延遲導入，在需要時才載入
faster_whisper = None
torch = None
yt_dlp = None
openai = None

# --- Bookmark Management ---
BOOKMARK_FILE = Path(__file__).parent / "bookmarks.json"

# 移除重複的模型變數，統一使用背景工作程序的模型
# model = None  # 移除這行
is_model_loading = False
model_load_lock = threading.Lock()

# 新增 GPU 狀態追蹤
gpu_status = {
    'device': 'unknown',
    'device_name': 'unknown',
    'cuda_available': False,
    'last_updated': None
}
gpu_status_lock = threading.Lock()

# --- GPU Status Functions ---
def get_gpu_status():
    """獲取 GPU 狀態資訊"""
    global gpu_status, torch

    with gpu_status_lock:
        try:
            # 延遲導入 torch
            if not torch:
                import torch as t
                torch = t

            current_time = datetime.now()

            # 基本設備資訊
            device = "cpu"
            device_name = "CPU"
            cuda_available = torch.cuda.is_available()

            if cuda_available:
                try:
                    # 測試 CUDA 是否真的可用
                    test_tensor = torch.zeros(1, device="cuda")
                    del test_tensor
                    device = "cuda"

                    # 獲取 GPU 資訊
                    device_name = torch.cuda.get_device_name(0)

                except Exception as e:
                    print(f"CUDA 測試失敗: {e}")
                    device = "cpu"
                    device_name = "CPU (CUDA 不可用)"
                    cuda_available = False
            else:
                memory_total = memory_reserved = memory_allocated = memory_free = 0
                gpu_utilization = 0

            # 更新狀態
            gpu_status.update({
                'device': device,
                'device_name': device_name,
                'cuda_available': cuda_available,
                'last_updated': utils_get_timestamp("default")
            })

            return gpu_status.copy()

        except Exception as e:
            print(f"獲取 GPU 狀態時發生錯誤: {e}")
            return gpu_status.copy()

def update_gpu_status():
    """更新 GPU 狀態並廣播給所有客戶端"""
    status = get_gpu_status()
    socketio.emit('gpu_status_update', status)

# --- App Configuration ---
# (folders are now defined inside the worker)

# --- Helper Functions (Main App) ---
def log_and_emit(message, level='info', sid=None):
    """Helper function to print to console and emit to client."""
    print(f"[{level.upper()}] {message}")

    # 儲存日誌到檔案
    if sid:
        save_log_entry(sid, message, level)

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

def queue_listener(res_queue):
    """Listens for messages from worker and emits them via SocketIO."""
    print("[LISTENER] Queue listener started.")
    while True:
        try:
            message = res_queue.get()
            if message == 'STOP': break

            event = message.get('event')
            data = message.get('data')
            sid = message.get('sid')

            if event == 'update_server_state':
                update_server_state(data.get('is_busy'), data.get('current_task'))
            elif event == 'gpu_status_update':
                # 更新全域 GPU 狀態
                with gpu_status_lock:
                    gpu_status.update(data)
                # 廣播給所有客戶端
                socketio.emit(event, data)
            elif event:
                if sid is None:
                    # 廣播到所有客戶端
                    socketio.emit(event, data)
                else:
                    # 發送到特定會話
                    socketio.emit(event, data, to=sid)
        except Exception as e:
            print(f"[LISTENER] Error: {e}")



# --- Core Processing Logic ---
def do_summarize(subtitle_content, summary_save_path, sid):
    """Performs summarization using OpenAI API."""
    try:
        from ai_summary_service import get_summary_service

        # 創建日誌回調函數
        def log_callback(message, level='info'):
            log_and_emit(message, level, sid)

        # 獲取摘要服務
        summary_service = get_summary_service(
            openai_api_key=get_config("OPENAI_API_KEY"),
            config_getter=get_config
        )

        # 生成並儲存摘要
        success, result = summary_service.generate_and_save_summary(
            subtitle_content=subtitle_content,
            save_path=Path(summary_save_path),
            prompt_type="simple",  # 保持原有的簡單模式
            log_callback=log_callback
        )

        if not success:
            log_and_emit(f"❌ AI 摘要失敗: {result}", 'error', sid)

    except Exception as e:
        log_and_emit(f"❌ AI 摘要失敗: {e}", 'error', sid)
        traceback.print_exc()

# _actual_transcribe_task 函數已移除，所有語音辨識由 worker process 處理

# do_transcribe 函數已移除，所有語音辨識由 worker process 處理

# 新增統一的任務入列函數



# --- Background Worker ---
def background_worker(task_q, result_q, stop_evt, download_p, summary_p, subtitle_p, openai_key):
    """重構後的背景工作程式 - 使用模組化設計"""
    from pathlib import Path
    from queue import Empty as QueueEmpty
    
    # 導入新的管理器（暫時使用相對導入，後續會改為絕對導入）
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))
        from services.background_worker_manager import BackgroundWorkerManager
    except ImportError:
        # 回退到原始實作（向後兼容）
        print("[WORKER] Cannot import new modules, falling back to legacy implementation")
        _legacy_background_worker(task_q, result_q, stop_evt, download_p, summary_p, subtitle_p, openai_key)
        return
    
    # 設定資料夾
    folders = {
        'download': Path(download_p),
        'summary': Path(summary_p),
        'subtitle': Path(subtitle_p)
    }
    
    # 建立工作程式管理器
    worker_manager = BackgroundWorkerManager(folders, openai_key)
    
    print("[WORKER] Ready.")
    while not stop_evt.is_set():
        try:
            task = task_q.get(timeout=1)
            if not task:
                continue

            print(f"[WORKER] DEBUG: 收到任務: {task}")
            
            # 檢查任務類型
            task_type = task.get('task_type', 'url')
            print(f"[WORKER] DEBUG: 任務類型: {task_type}")

            try:
                if task_type == 'audio_file':
                    print("[WORKER] DEBUG: 處理 audio_file 任務")
                    success = worker_manager.process_audio_file_task(task, result_q)
                else:
                    # 處理 URL 任務（YouTube等）
                    success = worker_manager.process_youtube_task(task, result_q)
                    
                if success:
                    print(f"[WORKER] Task completed successfully: {task.get('sid', 'unknown')}")
                else:
                    print(f"[WORKER] Task failed: {task.get('sid', 'unknown')}")
                    
            except Exception as e:
                print(f"[WORKER] Error processing task: {e}")
                import traceback
                print(f"[WORKER] Error details: {traceback.format_exc()}")
                
                # 發送錯誤給前端
                sid = task.get('sid')
                if sid:
                    result_q.put({
                        'event': 'update_log',
                        'data': {'log': f"❌ 處理時發生錯誤: {e}", 'type': 'error'},
                        'sid': sid
                    })
            finally:
                # 確保狀態重置
                sid = task.get('sid')
                if sid:
                    result_q.put({
                        'event': 'update_server_state',
                        'data': {'is_busy': False, 'current_task': '空閒'}
                    })
                    result_q.put({'event': 'processing_finished', 'data': {}, 'sid': sid})
                    
        except QueueEmpty:
            continue
        except Exception as e:
            print(f"[WORKER] Unexpected error in main loop: {e}")
            import traceback
            print(f"[WORKER] Error details: {traceback.format_exc()}")

    print("[WORKER] Shutting down.")


def _legacy_background_worker(task_q, result_q, stop_evt, download_p, summary_p, subtitle_p, openai_key):
    """原始的背景工作程式實作（向後兼容）"""
    import faster_whisper, torch, yt_dlp, openai, re
    from pathlib import Path

    # send_telegram_notification 已移至 utils.py
    def send_telegram_notification(message):
        return utils_send_telegram_notification(message)

    DOWNLOAD_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER = Path(download_p), Path(summary_p), Path(subtitle_p)

    def worker_emit(event, data, sid): result_q.put({'event': event, 'data': data, 'sid': sid})
    def worker_update_state(is_busy, task_desc): result_q.put({'event': 'update_server_state', 'data': {'is_busy': is_busy, 'current_task': task_desc}})

    # 使用統一的工具函數
    def sanitize_filename(f, ml=80):
        return utils_sanitize_filename(f, ml)

    def segments_to_srt(segs):
        return utils_segments_to_srt(segs)

    model = None
    try:
        # 嘗試使用 CUDA，如果失敗則降級到 CPU
        device = "cpu"
        compute = "int8"

        # 檢查 CUDA 是否真的可用
        if torch.cuda.is_available():
            try:
                # 測試 CUDA 是否真的可以工作
                test_tensor = torch.zeros(1, device="cuda")
                del test_tensor
                device = "cuda"
                compute = "float16"
                print(f"[WORKER] CUDA test successful, using GPU")
            except Exception as cuda_error:
                print(f"[WORKER] CUDA test failed: {cuda_error}, falling back to CPU")
                device = "cpu"
                compute = "int8"

        print(f"[WORKER] Loading model with device={device}, compute={compute}")
        model = faster_whisper.WhisperModel("asadfgglie/faster-whisper-large-v3-zh-TW", device=device, compute_type=compute)
        print("[WORKER] Model loaded successfully.")

        # 更新模型載入狀態並發送給主程序
        worker_gpu_status = {
            'device': device,
            'device_name': torch.cuda.get_device_name(0) if device == 'cuda' else 'CPU',
            'cuda_available': device == 'cuda',
            'last_updated': utils_get_timestamp("default")
        }

        # 廣播 GPU 狀態更新
        result_q.put({'event': 'gpu_status_update', 'data': worker_gpu_status})

    except Exception as e:
        print(f"[WORKER] FATAL: Could not load model: {e}")
        print(f"[WORKER] Error details: {traceback.format_exc()}")
        return

    print("[WORKER] Ready.")
    while not stop_evt.is_set():
        try:
            task = task_q.get(timeout=1)
            if not task: continue

            print(f"[WORKER] DEBUG: 收到任務: {task}")

            # 檢查任務類型
            task_type = task.get('task_type', 'url')
            print(f"[WORKER] DEBUG: 任務類型: {task_type}")

            if task_type == 'audio_file':
                print("[WORKER] DEBUG: 處理 audio_file 任務")
                # 處理音訊檔案任務
                sid = task.get('sid')
                audio_file = task.get('audio_file')
                subtitle_path = task.get('subtitle_path')
                summary_path = task.get('summary_path')

                print(f"[WORKER] DEBUG: sid={sid}, audio_file={audio_file}, subtitle_path={subtitle_path}, summary_path={summary_path}")

                if not (audio_file and subtitle_path and summary_path):
                    print("[WORKER] DEBUG: 任務資料不完整，跳過")
                    continue

                # 設定目前任務
                with task_lock:
                    current_task_sid = sid or "broadcast_task"

                worker_emit('update_log', {'log': "🔄 工作程序已接收音訊檔案任務...", 'type': 'info'}, sid)
                worker_update_state(True, f"處理音訊檔案: {Path(audio_file).name[:40]}...")

                try:
                    # 對於上傳檔案任務，不檢查取消狀態（因為是獨立進程）

                    # 檢查音檔是否存在
                    if not Path(audio_file).exists():
                        worker_emit('update_log', {'log': f"❌ 音檔不存在: {audio_file}", 'type': 'error'}, sid)
                        continue

                    # 檢查音檔大小
                    file_size = Path(audio_file).stat().st_size
                    worker_emit('update_log', {'log': f"📊 音檔大小: {file_size / (1024*1024):.1f} MB", 'type': 'info'}, sid)

                    # 上傳檔案任務不檢查取消狀態

                    worker_emit('update_log', {'log': "🎤 語音辨識中...", 'type': 'info'}, sid)

                    # 增加進度回報
                    worker_emit('update_log', {'log': "🔄 載入 Whisper 模型...", 'type': 'info'}, sid)
                    if not model:
                        worker_emit('update_log', {'log': "❌ Whisper 模型未載入", 'type': 'error'}, sid)
                        continue

                    worker_emit('update_log', {'log': "🎯 開始轉錄音檔...", 'type': 'info'}, sid)
                    try:
                        worker_emit('update_log', {'log': "🔄 正在初始化轉錄...", 'type': 'info'}, sid)

                        # 使用更簡單的參數進行轉錄
                        segments, _ = model.transcribe(
                            str(audio_file),
                            beam_size=1,  # 減少 beam_size
                            language="zh",  # 指定語言
                            vad_filter=True  # 啟用語音活動檢測
                        )

                        worker_emit('update_log', {'log': "🔄 轉錄進行中，正在處理片段...", 'type': 'info'}, sid)

                        # 將生成器轉換為列表以便計算長度
                        segments_list = list(segments)
                        worker_emit('update_log', {'log': f"✅ 轉錄完成，共 {len(segments_list)} 個片段", 'type': 'success'}, sid)
                    except RuntimeError as e:
                        if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                            worker_emit('update_log', {'log': "⚠️ CUDA 錯誤，嘗試使用 CPU 重新轉錄...", 'type': 'warning'}, sid)
                            try:
                                # 重新載入 CPU 模型
                                worker_emit('update_log', {'log': "🔄 重新載入 CPU 模型...", 'type': 'info'}, sid)
                                model = faster_whisper.WhisperModel("asadfgglie/faster-whisper-large-v3-zh-TW", device="cpu", compute_type="int8")

                                # 重新嘗試轉錄
                                segments, _ = model.transcribe(
                                    str(audio_file),
                                    beam_size=1,
                                    language="zh",
                                    vad_filter=True
                                )

                                worker_emit('update_log', {'log': "🔄 CPU 轉錄進行中...", 'type': 'info'}, sid)
                                segments_list = list(segments)
                                worker_emit('update_log', {'log': f"✅ CPU 轉錄完成，共 {len(segments_list)} 個片段", 'type': 'success'}, sid)
                            except Exception as cpu_error:
                                worker_emit('update_log', {'log': f"❌ CPU 轉錄也失敗: {cpu_error}", 'type': 'error'}, sid)
                                continue
                        else:
                            worker_emit('update_log', {'log': f"❌ 轉錄失敗: {e}", 'type': 'error'}, sid)
                            worker_emit('update_log', {'log': f"🔍 錯誤詳情: {traceback.format_exc()}", 'type': 'error'}, sid)
                            continue
                    except Exception as e:
                        worker_emit('update_log', {'log': f"❌ 轉錄失敗: {e}", 'type': 'error'}, sid)
                        worker_emit('update_log', {'log': f"🔍 錯誤詳情: {traceback.format_exc()}", 'type': 'error'}, sid)
                        continue

                    worker_emit('update_log', {'log': "📝 生成字幕檔案...", 'type': 'info'}, sid)
                    srt_content = segments_to_srt(segments_list)
                    Path(subtitle_path).write_text(srt_content, encoding='utf-8')
                    worker_emit('update_log', {'log': "📝 字幕已儲存", 'type': 'info'}, sid)

                    if srt_content:
                        # 上傳檔案任務不檢查取消狀態

                        try:
                            from ai_summary_service import get_summary_service

                            # 創建回調函數
                            def log_callback(message, level='info'):
                                worker_emit('update_log', {'log': message, 'type': level}, sid)

                            def telegram_callback(message):
                                send_telegram_notification(message)

                            # 獲取摘要服務
                            summary_service = get_summary_service(
                                openai_api_key=openai_key,
                                config_getter=lambda key, default=None: os.getenv(key, default)
                            )

                            # 準備header資訊
                            header_info = {
                                'filename': Path(audio_file).name
                            }

                            # 生成並儲存摘要
                            success, result = summary_service.generate_and_save_summary(
                                subtitle_content=srt_content,
                                save_path=Path(summary_path),
                                prompt_type="detailed",  # 使用詳細模式
                                header_info=header_info,
                                log_callback=log_callback,
                                telegram_callback=telegram_callback
                            )

                            if not success:
                                worker_emit('update_log', {'log': f"❌ 摘要生成失敗: {result}", 'type': 'error'}, sid)

                        except ImportError:
                            # 統一摘要服務不可用，直接報錯
                            error_msg = "❌ AI摘要服務模組不可用，請檢查 ai_summary_service.py"
                            worker_emit('update_log', {'log': error_msg, 'type': 'error'}, sid)

                    # 刪除音檔以節省空間
                    if Path(audio_file).exists():
                        try:
                            file_size_mb = Path(audio_file).stat().st_size / (1024*1024)
                            Path(audio_file).unlink()  # 刪除音檔
                            worker_emit('update_log', {'log': f"🗑️ 已刪除音檔 ({file_size_mb:.1f} MB) 以節省空間", 'type': 'info'}, sid)
                        except Exception as e:
                            worker_emit('update_log', {'log': f"⚠️ 刪除音檔時發生錯誤: {e}", 'type': 'warning'}, sid)

                except Exception as e:
                    worker_emit('update_log', {'log': f"❌ 處理音訊檔案時發生錯誤: {e}", 'type': 'error'}, sid)
                    traceback.print_exc()
                finally:
                    # 清除目前任務
                    with task_lock:
                        if current_task_sid == (sid or "broadcast_task"):
                            current_task_sid = None

                    worker_update_state(False, "空閒")
                    worker_emit('processing_finished', {}, sid)

            else:
                # 處理 URL 任務（原有邏輯）
                sid, url = task.get('sid'), task.get('audio_url')
                if not (sid and url): continue

                # 設定目前任務
                with task_lock:
                    current_task_sid = sid

                #worker_emit('update_log', {'log': "工作程序已接收任務...", 'type': 'info'}, sid)
                worker_update_state(True, f"處理中: {url[:40]}...")

                try:
                    # 檢查是否被取消
                    with task_lock:
                        if current_task_sid != sid:
                            worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                            continue

                    # 檢測 URL 類型並調用相應的處理函數
                    url_type = detect_url_type(url)
                    if url_type == 'youtube':
                        # 使用現有的 YouTube 處理邏輯
                        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                            info = ydl.extract_info(url, download=False)

                        if not info:
                            worker_emit('update_log', {'log': "❌ 無法獲取影片資訊", 'type': 'error'}, sid)
                            continue

                        # --- Send Telegram Notification ---
                        tg_message = (
                            f"*Whisper WebApp 開始處理*\n\n"
                            f"▶️ *頻道:* `{info.get('uploader', 'N/A')}`\n"
                            f"📄 *標題:* `{info.get('title', 'N/A')}`\n"
                            f"🔗 *網址:* {info.get('webpage_url', url)}"
                        )
                        send_telegram_notification(tg_message)
                        # ----------------------------------

                        # --- Send extended video info to frontend ---
                        upload_date = info.get('upload_date')
                        if upload_date:
                            upload_date = f"{upload_date[:4]}/{upload_date[4:6]}/{upload_date[6:]}"

                        video_info = {
                            'title': info.get('title', '未知標題'),
                            'uploader': info.get('uploader', '未知上傳者'),
                            'thumbnail': info.get('thumbnail', ''),
                            'duration_string': info.get('duration_string', '未知'),
                            'view_count': info.get('view_count', 0),
                            'upload_date': upload_date or '未知日期'
                        }
                        worker_emit('update_video_info', video_info, sid)
                        # ------------------------------------

                        date_str = utils_get_timestamp("date")
                        uploader = utils_sanitize_filename(info.get('uploader', '未知頻道'), 30)
                        title = utils_sanitize_filename(info.get('title', '未知標題'), 50)
                        base_fn = f"{date_str} - {uploader}-{title}"
                        subtitle_path = SUBTITLE_FOLDER / f"{base_fn}.srt"; summary_path = SUMMARY_FOLDER / f"{base_fn}.txt"

                        if summary_path.exists():
                            worker_emit('update_log', {'log': "✅ 找到摘要快取", 'type': 'success'}, sid)
                            worker_emit('update_log', {'log': f"---\n{summary_path.read_text(encoding='utf-8')}", 'type': 'info'}, sid)
                            continue

                        srt_content = subtitle_path.read_text(encoding='utf-8') if subtitle_path.exists() else None
                        if srt_content: worker_emit('update_log', {'log': "✅ 找到字幕快取", 'type': 'success'}, sid)
                        else:
                            # 檢查是否被取消
                            with task_lock:
                                if current_task_sid != sid:
                                    worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                                    continue

                            worker_emit('update_log', {'log': "📥 下載音檔中...", 'type': 'info'}, sid)
                            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': str(DOWNLOAD_FOLDER / f"{base_fn}.%(ext)s"), 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}], 'quiet':True}
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
                            audio_file = DOWNLOAD_FOLDER / f"{base_fn}.mp3"
                            if not audio_file.exists(): raise FileNotFoundError("下載的音檔不存在")

                            # 檢查音檔大小
                            file_size = audio_file.stat().st_size
                            worker_emit('update_log', {'log': f"📊 音檔大小: {file_size / (1024*1024):.1f} MB", 'type': 'info'}, sid)

                            # 檢查是否被取消
                            with task_lock:
                                if current_task_sid != sid:
                                    worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                                    continue

                            worker_emit('update_log', {'log': "🎤 語音辨識中...", 'type': 'info'}, sid)

                            # 增加進度回報
                            worker_emit('update_log', {'log': "🔄 載入 Whisper 模型...", 'type': 'info'}, sid)
                            if not model:
                                worker_emit('update_log', {'log': "❌ Whisper 模型未載入", 'type': 'error'}, sid)
                                continue

                            worker_emit('update_log', {'log': "🎯 開始轉錄音檔...", 'type': 'info'}, sid)
                            try:
                                worker_emit('update_log', {'log': "🔄 正在初始化轉錄...", 'type': 'info'}, sid)

                                # 使用更簡單的參數進行轉錄
                                segments, _ = model.transcribe(
                                    str(audio_file),
                                    beam_size=1,  # 減少 beam_size
                                    language="zh",  # 指定語言
                                    vad_filter=True  # 啟用語音活動檢測
                                )

                                worker_emit('update_log', {'log': "🔄 轉錄進行中，正在處理片段...", 'type': 'info'}, sid)

                                # 將生成器轉換為列表以便計算長度
                                segments_list = list(segments)
                                worker_emit('update_log', {'log': f"✅ 轉錄完成，共 {len(segments_list)} 個片段", 'type': 'success'}, sid)
                            except RuntimeError as e:
                                if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                                    worker_emit('update_log', {'log': "⚠️ CUDA 錯誤，嘗試使用 CPU 重新轉錄...", 'type': 'warning'}, sid)
                                    try:
                                        # 重新載入 CPU 模型
                                        worker_emit('update_log', {'log': "🔄 重新載入 CPU 模型...", 'type': 'info'}, sid)
                                        model = faster_whisper.WhisperModel("asadfgglie/faster-whisper-large-v3-zh-TW", device="cpu", compute_type="int8")

                                        # 重新嘗試轉錄
                                        segments, _ = model.transcribe(
                                            str(audio_file),
                                            beam_size=1,
                                            language="zh",
                                            vad_filter=True
                                        )

                                        worker_emit('update_log', {'log': "🔄 CPU 轉錄進行中...", 'type': 'info'}, sid)
                                        segments_list = list(segments)
                                        worker_emit('update_log', {'log': f"✅ CPU 轉錄完成，共 {len(segments_list)} 個片段", 'type': 'success'}, sid)
                                    except Exception as cpu_error:
                                        worker_emit('update_log', {'log': f"❌ CPU 轉錄也失敗: {cpu_error}", 'type': 'error'}, sid)
                                        continue
                                else:
                                    worker_emit('update_log', {'log': f"❌ 轉錄失敗: {e}", 'type': 'error'}, sid)
                                    worker_emit('update_log', {'log': f"🔍 錯誤詳情: {traceback.format_exc()}", 'type': 'error'}, sid)
                                    continue
                            except Exception as e:
                                worker_emit('update_log', {'log': f"❌ 轉錄失敗: {e}", 'type': 'error'}, sid)
                                worker_emit('update_log', {'log': f"🔍 錯誤詳情: {traceback.format_exc()}", 'type': 'error'}, sid)
                                continue

                            worker_emit('update_log', {'log': "📝 生成字幕檔案...", 'type': 'info'}, sid)
                            srt_content = segments_to_srt(segments_list)
                            subtitle_path.write_text(srt_content, encoding='utf-8')
                            worker_emit('update_log', {'log': "📝 字幕已儲存", 'type': 'info'}, sid)

                        if srt_content:
                            # 檢查是否被取消
                            with task_lock:
                                if current_task_sid != sid:
                                    worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                                    continue

                            # 使用統一摘要服務
                            try:
                                from ai_summary_service import get_summary_service

                                # 設定回調函數
                                def log_callback(message, level='info'):
                                    worker_emit('update_log', {'log': message, 'type': level}, sid)

                                def telegram_callback(message):
                                    send_telegram_notification(message)

                                # 準備 header 資訊
                                header_info = {
                                    'title': info.get('title', '未知標題'),
                                    'uploader': info.get('uploader', '未知頻道'),
                                    'url': info.get('webpage_url', url)
                                }

                                # 獲取摘要服務並生成摘要
                                summary_service = get_summary_service(openai_key, get_config)
                                success, result = summary_service.generate_and_save_summary(
                                    subtitle_content=srt_content,
                                    save_path=summary_path,
                                    prompt_type="structured",
                                    header_info=header_info,
                                    log_callback=log_callback,
                                    telegram_callback=telegram_callback
                                )

                                if not success:
                                    worker_emit('update_log', {'log': f"❌ 摘要生成失敗: {result}", 'type': 'error'}, sid)

                            except ImportError:
                                # 統一摘要服務不可用，直接報錯
                                error_msg = "❌ AI摘要服務模組不可用，請檢查 ai_summary_service.py"
                                worker_emit('update_log', {'log': error_msg, 'type': 'error'}, sid)

                        # 刪除音檔以節省空間
                        if 'audio_file' in locals() and audio_file.exists():
                            try:
                                file_size_mb = audio_file.stat().st_size / (1024*1024)
                                audio_file.unlink()  # 刪除音檔
                                worker_emit('update_log', {'log': f"🗑️ 已刪除音檔 ({file_size_mb:.1f} MB) 以節省空間", 'type': 'info'}, sid)
                            except Exception as e:
                                worker_emit('update_log', {'log': f"⚠️ 刪除音檔時發生錯誤: {e}", 'type': 'warning'}, sid)
                    else:
                        # 檢測 URL 類型並處理其他平台
                        worker_emit('update_log', {'log': f"❌ 不支援的 URL 類型，目前只支援 YouTube", 'type': 'error'}, sid)
                except Exception as e:
                    worker_emit('update_log', {'log': f"❌ 處理時發生錯誤: {e}", 'type': 'error'}, sid)
                    traceback.print_exc()
                finally:
                    # 清除目前任務
                    with task_lock:
                        if current_task_sid == sid:
                            current_task_sid = None

                    worker_update_state(False, "空閒")
                    worker_emit('processing_finished', {}, sid)
        except QueueEmpty: continue
    print("[WORKER] Shutting down.")

# --- Flask Routes and Handlers ---
@app.route('/')
def index(): return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    sid = request.sid; print(f"Client connected: {sid}")

    # 載入之前的日誌記錄
    previous_logs = get_session_logs(sid)
    if previous_logs.strip():
        # 發送之前的日誌記錄
        for line in previous_logs.strip().split('\n'):
            if line.strip():
                socketio.emit('update_log', {'log': line.strip(), 'type': 'info'}, to=sid)

    with state_lock: emit('server_status_update', SERVER_STATE)

    # 發送 GPU 狀態
    gpu_status = get_gpu_status()
    socketio.emit('gpu_status_update', gpu_status, to=sid)

    log_and_emit('成功連接至後端伺服器。', 'success', sid)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Client disconnected: {sid}")

    # 延遲清理日誌檔案（給使用者時間重新連線）
    def delayed_cleanup():
        time.sleep(30)  # 等待 30 秒
        clear_session_logs(sid)

    # 在背景執行清理
    threading.Thread(target=delayed_cleanup, daemon=True).start()

@socketio.on('clear_logs')
def handle_clear_logs():
    """處理清除日誌請求"""
    sid = request.sid
    clear_session_logs(sid)
    log_and_emit('日誌記錄已清除', 'info', sid)

@socketio.on('start_processing')
def handle_start_processing(data):
    sid = request.sid
    client_ip = get_client_ip()

    if not (isinstance(data, dict) and data.get('audio_url') and data.get('access_code') is not None):
        return log_and_emit("🔴 錯誤：請求格式不正確。", 'error', sid)

    # 檢查 IP 是否被封鎖
    if is_ip_blocked(client_ip):
        remaining_time = get_block_remaining_time(client_ip)
        minutes = remaining_time // 60
        seconds = remaining_time % 60
        return log_and_emit(f"🔒 您的 IP 已被暫時封鎖，請等待 {minutes} 分 {seconds} 秒後再試。", 'error', sid)

    # 驗證通行碼
    access_code = get_config("ACCESS_CODE")
    if access_code and data.get('access_code') != access_code:
        # 記錄失敗嘗試
        record_failed_attempt(client_ip)
        remaining_attempts = get_remaining_attempts(client_ip)

        if remaining_attempts > 0:
            log_and_emit(f"🔴 錯誤：通行碼不正確。剩餘嘗試次數：{remaining_attempts}", 'error', sid)
        else:
            # 已達到最大嘗試次數，IP 被封鎖
            log_and_emit(f"🔒 錯誤：通行碼不正確。您的 IP 已被封鎖 {BLOCK_DURATION//60} 分鐘。", 'error', sid)

        # 發送通行碼錯誤事件，讓前端重新啟用輸入框
        socketio.emit('access_code_error', {'message': '通行碼錯誤'}, to=sid)
        return

    # 通行碼正確，記錄成功並重置計數器
    record_successful_attempt(client_ip)

    # 使用新的任務佇列系統
    from task_queue import get_task_queue

    task_queue_manager = get_task_queue()

    try:
        # 記錄收到的請求
        url = data.get('audio_url')
        log_and_emit(f"收到請求，準備處理網址: {url}", 'info', sid)

        # 添加任務到佇列 (使用字符串而不是枚舉)
        task_id = task_queue_manager.add_task(
            task_type='youtube',
            data={'url': url},
            user_ip=client_ip,
            priority=5  # 默認優先級
        )

        # 獲取佇列位置
        queue_position = task_queue_manager.get_user_queue_position(task_id)

        if queue_position > 1:
            log_and_emit(f"⏳ 任務已加入佇列，目前排隊位置：第 {queue_position} 位，任務ID：{task_id[:8]}", 'warning', sid)
        else:
            log_and_emit(f'✅ 任務已接收並開始處理，任務ID：{task_id[:8]}', 'success', sid)

    except Exception as e:
        log_and_emit(f"❌ 加入佇列失敗：{str(e)}", 'error', sid)

@socketio.on('cancel_processing')
def handle_cancel_processing():
    sid = request.sid
    global current_task_sid

    with task_lock:
        if current_task_sid == sid:
            current_task_sid = None
            log_and_emit("🛑 任務已取消", 'info', sid)
            update_server_state(False, "空閒")
            socketio.emit('processing_finished', {}, to=sid)
        else:
            log_and_emit("❌ 沒有可取消的任務", 'error', sid)

@app.route('/summary')
def list_summaries():
    if not SUMMARY_FOLDER.exists(): return "摘要資料夾不存在。", 500
    files = sorted(SUMMARY_FOLDER.glob('*.txt'), key=os.path.getmtime, reverse=True)

    # 為每個摘要加入書籤狀態資訊
    summaries_with_bookmark_status = []
    for f in files:
        summaries_with_bookmark_status.append({
            'filename': f.name,
            'is_bookmarked': is_bookmarked(f.name)
        })

    return render_template('summaries.html', summaries=summaries_with_bookmark_status)

@app.route('/summary/<filename>')
def show_summary(filename):
    # 對於摘要檔案，我們需要先檢查原始檔名，因為它們來自可信的摘要列表
    # URL解碼檔案名稱以處理特殊字符
    from urllib.parse import unquote
    decoded_filename = unquote(filename)
    safe_path = SUMMARY_FOLDER / decoded_filename

    # 安全檢查：確保路徑不會逃出指定目錄且檔案存在
    try:
        safe_path = safe_path.resolve()
        SUMMARY_FOLDER_RESOLVED = SUMMARY_FOLDER.resolve()

        # 檢查路徑是否在摘要資料夾內
        if not str(safe_path).startswith(str(SUMMARY_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400

        # 檢查檔案是否存在
        if not safe_path.exists():
            return "檔案不存在", 404

        # 檢查是否為 .txt 檔案
        if safe_path.suffix.lower() != '.txt':
            return "檔案類型不支援", 400

    except Exception:
        return "檔案路徑無效", 400

    content = safe_path.read_text(encoding='utf-8')

    # 檢查對應的字幕檔案是否存在
    subtitle_filename = safe_path.stem + '.srt'
    subtitle_path = SUBTITLE_FOLDER / subtitle_filename
    has_subtitle = subtitle_path.exists()

    return render_template('summary_detail.html',
                         title=safe_path.stem,
                         content=content,
                         filename=safe_path.name,
                         has_subtitle=has_subtitle)

@app.route('/download/summary/<filename>')
def download_summary(filename):
    """下載摘要檔案"""
    try:
        # URL解碼檔案名稱
        from urllib.parse import unquote
        filename = unquote(filename)

        # 安全路徑檢查
        safe_path = (SUMMARY_FOLDER / filename).resolve()
        SUMMARY_FOLDER_RESOLVED = SUMMARY_FOLDER.resolve()

        if not str(safe_path).startswith(str(SUMMARY_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400

        if not safe_path.exists():
            return "檔案不存在", 404

        if safe_path.suffix.lower() != '.txt':
            return "檔案類型不支援", 400

        return send_file(safe_path, as_attachment=True, download_name=filename)

    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@app.route('/download/subtitle/<filename>')
def download_subtitle(filename):
    """下載字幕檔案"""
    try:
        # URL解碼檔案名稱
        from urllib.parse import unquote
        filename = unquote(filename)

        # 將 .txt 副檔名改為 .srt
        if filename.endswith('.txt'):
            filename = filename[:-4] + '.srt'
        elif not filename.endswith('.srt'):
            filename += '.srt'

        # 安全路徑檢查
        safe_path = (SUBTITLE_FOLDER / filename).resolve()
        SUBTITLE_FOLDER_RESOLVED = SUBTITLE_FOLDER.resolve()

        if not str(safe_path).startswith(str(SUBTITLE_FOLDER_RESOLVED)):
            return "檔案路徑無效", 400

        if not safe_path.exists():
            return "字幕檔案不存在", 404

        if safe_path.suffix.lower() != '.srt':
            return "檔案類型不支援", 400

        return send_file(safe_path, as_attachment=True, download_name=filename)

    except Exception as e:
        return f"下載失敗: {str(e)}", 500

@app.route('/trash')
def trash_page():
    """回收桶頁面"""
    trash_items = get_trash_items()
    return render_template('trash.html', trash_items=trash_items)

@app.route('/api/trash/move', methods=['POST'])
def api_move_to_trash():
    """API: 移動檔案到回收桶"""
    try:
        data = request.get_json()
        if not data or 'files' not in data:
            return jsonify({'success': False, 'message': '缺少檔案列表'}), 400

        results = []
        for file_info in data['files']:
            file_path = file_info.get('path')
            file_type = file_info.get('type', 'summary')

            if not file_path:
                results.append({'success': False, 'message': '缺少檔案路徑'})
                continue

            success, message = move_file_to_trash(file_path, file_type)
            results.append({
                'success': success,
                'message': message,
                'file_path': file_path
            })

        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'操作失敗: {str(e)}'}), 500

@app.route('/api/trash/restore', methods=['POST'])
def api_restore_from_trash():
    """API: 從回收桶還原檔案"""
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return jsonify({'success': False, 'message': '缺少回收桶項目ID'}), 400

        trash_id = data['trash_id']
        success, message = restore_file_from_trash(trash_id)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'還原失敗: {str(e)}'}), 500

@app.route('/api/trash/delete', methods=['POST'])
def api_delete_from_trash():
    """API: 從回收桶永久刪除檔案"""
    try:
        data = request.get_json()
        if not data or 'trash_id' not in data:
            return jsonify({'success': False, 'message': '缺少回收桶項目ID'}), 400

        trash_id = data['trash_id']
        success, message = delete_file_from_trash(trash_id)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500

@app.route('/api/trash/list')
def api_get_trash_list():
    """API: 獲取回收桶列表"""
    try:
        trash_items = get_trash_items()
        return jsonify({
            'success': True,
            'items': trash_items
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'獲取列表失敗: {str(e)}'}), 500

# --- Bookmark API Routes ---
@app.route('/bookmarks')
def bookmarks_page():
    """書籤頁面"""
    try:
        bookmarks = get_bookmarks()
        return render_template('bookmarks.html', bookmarks=bookmarks)
    except Exception as e:
        return f"Error loading bookmarks page: {e}", 500

@app.route('/api/bookmarks/add', methods=['POST'])
def api_add_bookmark():
    """API: 新增書籤"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        title = data.get('title')

        if not filename:
            return jsonify({'success': False, 'message': '檔案名稱不能為空'})

        success, message = add_bookmark(filename, title)
        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/bookmarks/remove', methods=['POST'])
def api_remove_bookmark():
    """API: 移除書籤"""
    try:
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return jsonify({'success': False, 'message': '檔案名稱不能為空'})

        success, message = remove_bookmark(filename)
        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/bookmarks/list')
def api_get_bookmarks():
    """API: 獲取書籤列表"""
    try:
        bookmarks = get_bookmarks()
        return jsonify({
            'success': True,
            'bookmarks': bookmarks,
            'count': len(bookmarks)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/bookmarks/check/<filename>')
def api_check_bookmark(filename):
    """API: 檢查檔案是否已加入書籤"""
    try:
        is_bookmarked_result = is_bookmarked(filename)
        return jsonify({
            'success': True,
            'is_bookmarked': is_bookmarked_result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/login-attempts')
def admin_login_attempts():
    """管理端點：查看登入嘗試狀態"""
    admin_code = os.getenv("ADMIN_CODE")
    if not admin_code or request.args.get('code') != admin_code:
        return "未授權訪問", 401

    with attempts_lock:
        current_time = time.time()
        attempts_info = []

        for ip, data in LOGIN_ATTEMPTS.items():
            remaining_attempts = MAX_ATTEMPTS - data['count']
            is_blocked = 'blocked_until' in data and current_time < data['blocked_until']
            block_remaining = get_block_remaining_time(ip) if is_blocked else 0

            attempts_info.append({
                'ip': ip,
                'attempts': data['count'],
                'remaining': remaining_attempts,
                'first_attempt': datetime.fromtimestamp(data['first_attempt']).strftime('%Y-%m-%d %H:%M:%S'),
                'is_blocked': is_blocked,
                'block_remaining': f"{block_remaining//60}分{block_remaining%60}秒" if block_remaining > 0 else "無"
            })

    return render_template('admin_login_attempts.html', attempts=attempts_info, max_attempts=MAX_ATTEMPTS, block_duration=BLOCK_DURATION//60)

@app.route('/api/process', methods=['POST'])
def api_process_youtube():
    """API 端點：處理 YouTube URL 請求"""
    try:
        # 檢查請求格式
        if not request.is_json:
            return jsonify({
                'status': 'error',
                'message': '請求格式錯誤，需要 JSON 格式'
            }), 400

        data = request.get_json()
        youtube_url = data.get('youtube_url', '').strip()
        access_code = data.get('access_code', '').strip()

        if not youtube_url:
            return jsonify({
                'status': 'error',
                'message': '缺少 youtube_url 參數'
            }), 400

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'status': 'error',
                'message': '通行碼錯誤'
            }), 401

        # 加強 URL 驗證
        youtube_pattern = r'^https?://(www\.)?(youtube\.com|youtu\.be)/.+'
        if not re.match(youtube_pattern, youtube_url, re.IGNORECASE):
            return jsonify({
                'status': 'error',
                'message': '請輸入有效的 YouTube 網址 (必須包含 https:// 或 http://)'
            }), 400

        # 限制 URL 長度防止過長攻擊
        if len(youtube_url) > 500:
            return jsonify({
                'status': 'error',
                'message': 'URL 長度超過限制'
            }), 400

        # 伺服器忙碌時也可以接受任務，將加入佇列等待處理

        # 使用新的任務佇列系統
        user_ip = get_client_ip()
        queue_manager = get_task_queue()

        # 準備任務資料，嘗試提取影片ID以改善顯示
        task_data = {
            'url': youtube_url
        }

        # 嘗試從URL提取影片ID
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(youtube_url)

            if 'youtube.com' in parsed_url.netloc:
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
                if video_id:
                    task_data['video_id'] = video_id
                    task_data['display_name'] = f"YouTube 影片 ({video_id})"
            elif 'youtu.be' in parsed_url.netloc:
                video_id = parsed_url.path.lstrip('/')
                if video_id:
                    task_data['video_id'] = video_id
                    task_data['display_name'] = f"YouTube 影片 ({video_id})"
        except Exception as e:
            print(f"無法解析YouTube URL: {e}")
            # 如果解析失敗，使用預設顯示名稱
            task_data['display_name'] = "YouTube 影片"

        # 將任務加入佇列
        queue_task_id = queue_manager.add_task('youtube', task_data, priority=5, user_ip=user_ip)

        # 獲取佇列位置
        queue_position = queue_manager.get_user_queue_position(queue_task_id)

        return jsonify({
            'status': 'processing',
            'message': f'YouTube任務已加入佇列，目前排隊位置: {queue_position}',
            'task_id': queue_task_id,
            'queue_position': queue_position,
            'youtube_url': youtube_url
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'處理請求時發生錯誤：{str(e)}'
        }), 500

@socketio.on('request_gpu_status')
def handle_request_gpu_status():
    """處理客戶端請求 GPU 狀態"""
    sid = request.sid
    gpu_status = get_gpu_status()
    socketio.emit('gpu_status_update', gpu_status, to=sid)

# --- URL Processing Functions ---
def detect_url_type(url):
    """檢測 URL 類型並返回相應的處理器"""
    url_lower = url.lower()

    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    else:
        return 'unknown'

def validate_url(url, url_type):
    """驗證 URL 格式是否正確"""
    if url_type == 'youtube':
        return 'youtube.com' in url or 'youtu.be' in url
    else:
        return False

















# --- Trash System Functions ---
def load_trash_metadata():
    """載入回收桶記錄"""
    try:
        if TRASH_METADATA_FILE.exists():
            with open(TRASH_METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        return []
    except Exception as e:
        print(f"Error loading trash metadata: {e}")
        return []

def save_trash_metadata(metadata):
    """儲存回收桶記錄"""
    try:
        with open(TRASH_METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving trash metadata: {e}")

def move_file_to_trash(file_path, file_type):
    """移動檔案到回收桶"""
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return False, "檔案不存在"

        # 建立回收桶子資料夾
        trash_subfolder = TRASH_FOLDER / file_type
        trash_subfolder.mkdir(parents=True, exist_ok=True)

        # 生成唯一檔名
        timestamp = utils_get_timestamp("file")
        unique_id = str(uuid.uuid4())[:8]
        safe_name = utils_sanitize_filename(file_path.name)
        new_filename = f"{timestamp}_{unique_id}_{safe_name}"
        trash_path = trash_subfolder / new_filename

        # 移動檔案
        shutil.move(str(file_path), str(trash_path))

        # 記錄到回收桶
        metadata = load_trash_metadata()
        trash_record = {
            'id': str(uuid.uuid4()),
            'original_path': str(file_path),
            'trash_path': str(trash_path),
            'original_name': safe_name,
            'file_type': file_type,
            'deleted_at': datetime.now().isoformat(),
            'file_size': trash_path.stat().st_size if trash_path.exists() else 0
        }
        metadata.append(trash_record)
        save_trash_metadata(metadata)

        return True, "檔案已移動到回收桶"
    except Exception as e:
        return False, f"移動檔案失敗: {e}"

def restore_file_from_trash(trash_id):
    """從回收桶還原檔案"""
    try:
        metadata = load_trash_metadata()
        record = None
        record_index = None

        for i, item in enumerate(metadata):
            if item['id'] == trash_id:
                record = item
                record_index = i
                break

        if not record or record_index is None:
            return False, "找不到回收桶記錄"

        trash_path = Path(record['trash_path'])
        if not trash_path.exists():
            return False, "回收桶中的檔案不存在"

        # 決定還原位置
        if record['file_type'] == 'summary':
            restore_path = SUMMARY_FOLDER / utils_sanitize_filename(record['original_name'])
        elif record['file_type'] == 'subtitle':
            restore_path = SUBTITLE_FOLDER / utils_sanitize_filename(record['original_name'])
        else:
            return False, "不支援的檔案類型"

        # 檢查目標位置是否已有檔案
        if restore_path.exists():
            # 如果檔案已存在，添加時間戳
            timestamp = utils_get_timestamp("file")
            name_parts = restore_path.stem, restore_path.suffix
            restore_path = restore_path.parent / f"{name_parts[0]}_{timestamp}{name_parts[1]}"

        # 移動檔案回原位置
        shutil.move(str(trash_path), str(restore_path))

        # 從回收桶記錄中移除
        metadata.pop(record_index)
        save_trash_metadata(metadata)

        return True, "檔案已還原"
    except Exception as e:
        return False, f"還原檔案失敗: {e}"

def delete_file_from_trash(trash_id):
    """從回收桶永久刪除檔案"""
    try:
        metadata = load_trash_metadata()
        record = None
        record_index = None

        for i, item in enumerate(metadata):
            if item['id'] == trash_id:
                record = item
                record_index = i
                break

        if not record or record_index is None:
            return False, "找不到回收桶記錄"

        trash_path = Path(record['trash_path'])
        if trash_path.exists():
            trash_path.unlink()  # 刪除檔案

        # 從回收桶記錄中移除
        metadata.pop(record_index)
        save_trash_metadata(metadata)

        return True, "檔案已永久刪除"
    except Exception as e:
        return False, f"刪除檔案失敗: {e}"

def get_trash_items():
    """獲取回收桶中的所有項目"""
    if file_manager:
        return file_manager.get_trash_items()
    else:
        # 回退到原始實作
        try:
            metadata = load_trash_metadata()
            # 按刪除時間倒序排列
            metadata.sort(key=lambda x: x['deleted_at'], reverse=True)
            return metadata
        except Exception as e:
            print(f"Error getting trash items: {e}")
            return []

# --- Bookmark Management Functions ---
def load_bookmarks():
    """載入書籤資料"""
    if file_manager:
        bookmarks_data = file_manager.load_bookmarks()
        if not bookmarks_data or 'bookmarks' not in bookmarks_data:
            return {'bookmarks': []}
        return bookmarks_data
    else:
        # 回退到原始實作
        try:
            if BOOKMARK_FILE.exists():
                with open(BOOKMARK_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {'bookmarks': []}
        except Exception as e:
            print(f"Error loading bookmarks: {e}")
            return {'bookmarks': []}

def save_bookmarks(bookmarks_data):
    """儲存書籤資料"""
    if file_manager:
        return file_manager.save_bookmarks(bookmarks_data)
    else:
        # 回退到原始實作
        try:
            with open(BOOKMARK_FILE, 'w', encoding='utf-8') as f:
                json.dump(bookmarks_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving bookmarks: {e}")
            return False

def add_bookmark(filename, title=None):
    """新增書籤"""
    try:
        bookmarks_data = load_bookmarks()
        # 直接使用原始檔名，不要過度清理
        # 檢查是否已經是書籤
        for bookmark in bookmarks_data['bookmarks']:
            if bookmark['filename'] == filename:
                return False, "此摘要已在書籤中"
        # 如果沒有提供標題，從檔名提取
        if not title:
            title = filename.replace('.txt', '').replace('_', ' ')
        bookmark = {
            'filename': filename,
            'title': title,
            'added_date': datetime.now().isoformat(),
            'file_size': 0,
            'summary_preview': ""
        }
        # 嘗試獲取檔案資訊
        try:
            summary_path = SUMMARY_FOLDER / filename
            if summary_path.exists():
                bookmark['file_size'] = summary_path.stat().st_size
                with open(summary_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')[:3]
                    bookmark['summary_preview'] = '\n'.join(lines)[:200] + ('...' if len(content) > 200 else '')
        except Exception as e:
            print(f"Error reading summary file: {e}")
        bookmarks_data['bookmarks'].append(bookmark)
        save_bookmarks(bookmarks_data)
        return True, "書籤已新增"
    except Exception as e:
        print(f"Error adding bookmark: {e}")
        return False, f"新增書籤失敗: {e}"

def remove_bookmark(filename):
    """移除書籤"""
    try:
        bookmarks_data = load_bookmarks()
        original_length = len(bookmarks_data['bookmarks'])

        bookmarks_data['bookmarks'] = [
            bookmark for bookmark in bookmarks_data['bookmarks']
            if bookmark['filename'] != filename
        ]

        if len(bookmarks_data['bookmarks']) < original_length:
            save_bookmarks(bookmarks_data)
            return True, "書籤已移除"
        else:
            return False, "書籤不存在"

    except Exception as e:
        print(f"Error removing bookmark: {e}")
        return False, f"移除書籤失敗: {e}"

def is_bookmarked(filename):
    """檢查檔案是否已加入書籤"""
    try:
        bookmarks_data = load_bookmarks()
        return any(bookmark['filename'] == filename for bookmark in bookmarks_data['bookmarks'])
    except Exception as e:
        print(f"Error checking bookmark: {e}")
        return False

def get_bookmarks():
    """獲取所有書籤"""
    try:
        bookmarks_data = load_bookmarks()
        bookmarks = bookmarks_data.get('bookmarks', [])
        # 按新增時間倒序排列
        bookmarks.sort(key=lambda x: x.get('added_date', ''), reverse=True)
        return bookmarks
    except Exception as e:
        print(f"Error getting bookmarks: {e}")
        return []

@app.route('/api/system/config-status')
def api_get_config_status():
    """API: 獲取系統配置狀態"""
    try:
        access_code = get_config("ACCESS_CODE")
        openai_key = get_config("OPENAI_API_KEY")

        return jsonify({
            'success': True,
            'has_access_code': bool(access_code),
            'has_openai_key': bool(openai_key)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'獲取配置狀態失敗: {str(e)}'
        }), 500

@app.route('/api/verify_access_code', methods=['POST'])
def api_verify_access_code():
    """API: 驗證通行碼"""
    try:
        # 獲取通行碼參數
        access_code = request.form.get('access_code', '').strip()

        # 檢查系統是否設定了通行碼
        system_access_code = get_config("ACCESS_CODE")

        if not system_access_code:
            # 系統沒有設定通行碼，直接通過
            return jsonify({
                'success': True,
                'message': '系統未設定通行碼，無需驗證'
            })

        if access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        return jsonify({
            'success': True,
            'message': '通行碼驗證成功'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'驗證通行碼時發生錯誤：{str(e)}'
        }), 500

@app.route('/api/upload_subtitle', methods=['POST'])
def api_upload_subtitle():
    """API: 上傳字幕檔案到 summaries 目錄"""
    try:
        # 檢查請求格式
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': '請求格式錯誤，需要 JSON 格式'
            }), 400

        data = request.get_json()

        # 檢查必要參數
        filename = data.get('filename', '').strip()
        content = data.get('content', '')
        access_code = data.get('access_code', '').strip()

        if not filename:
            return jsonify({
                'success': False,
                'message': '缺少檔案名稱參數'
            }), 400

        if not content:
            return jsonify({
                'success': False,
                'message': '缺少檔案內容參數'
            }), 400

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        # 檔案名稱安全處理
        safe_filename = filename
        if not safe_filename:
            return jsonify({
                'success': False,
                'message': '檔案名稱無效'
            }), 400

        # 確保檔案名稱有 .txt 副檔名
        if not safe_filename.lower().endswith('.txt'):
            safe_filename += '.txt'

        # 檢查檔案是否已存在
        file_path = SUMMARY_FOLDER / safe_filename
        if file_path.exists():
            return jsonify({
                'success': False,
                'message': f'檔案 {safe_filename} 已存在'
            }), 409

        # 限制檔案內容大小 (最大 10MB)
        if len(content.encode('utf-8')) > 10 * 1024 * 1024:
            return jsonify({
                'success': False,
                'message': '檔案內容過大，最大限制 10MB'
            }), 413

        # 確保 summaries 目錄存在
        SUMMARY_FOLDER.mkdir(exist_ok=True)

        # 寫入檔案
        file_path.write_text(content, encoding='utf-8')

        return jsonify({
            'success': True,
            'message': '檔案上傳成功',
            'filename': safe_filename,
            'path': str(file_path),
            'size': len(content.encode('utf-8'))
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'上傳檔案時發生錯誤：{str(e)}'
        }), 500

@app.route('/api/upload_media', methods=['POST'])
def api_upload_media():
    """API: 上傳影音檔案並開始處理"""
    try:
        # 檢查是否有檔案上傳
        if 'media_file' not in request.files:
            return jsonify({
                'success': False,
                'message': '沒有選擇檔案'
            }), 400

        file = request.files['media_file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': '沒有選擇檔案'
            }), 400

        # 獲取通行碼參數
        access_code = request.form.get('access_code', '').strip()

        # 從檔案名稱自動提取標題
        title = os.path.splitext(file.filename)[0] if file.filename else ""

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        # 檢查檔案大小 (500MB 限制)
        file.seek(0, 2)  # 移動到檔案末尾
        file_size = file.tell()
        file.seek(0)  # 回到檔案開頭

        max_size = 500 * 1024 * 1024  # 500MB
        if file_size > max_size:
            return jsonify({
                'success': False,
                'message': f'檔案過大，最大限制 500MB，目前檔案 {file_size / (1024*1024):.1f}MB'
            }), 413

        # 檢查檔案格式
        allowed_extensions = {
            '.mp3', '.mp4', '.wav', '.m4a', '.flv', '.avi', '.mov',
            '.mkv', '.webm', '.ogg', '.aac', '.wma', '.wmv', '.3gp'
        }

        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'message': f'不支援的檔案格式：{file_ext}。支援格式：{", ".join(sorted(allowed_extensions))}'
            }), 400

        # 伺服器忙碌時也可以接受任務，將加入佇列等待處理

        # 生成安全的檔案名稱
        timestamp = utils_get_timestamp("file")
        safe_title = utils_sanitize_filename(title) if title else "未命名"
        task_id = str(uuid.uuid4())[:8]

        # 保持原始副檔名
        safe_filename = f"{timestamp}_{task_id}_{safe_title}{file_ext}"

        # 確保上傳目錄存在
        UPLOAD_FOLDER.mkdir(exist_ok=True)

        # 儲存檔案
        file_path = UPLOAD_FOLDER / safe_filename
        file.save(str(file_path))

        # 生成字幕和摘要檔案路徑（使用點號格式）
        date_str = utils_get_timestamp("date")
        base_name = f"{date_str} - {safe_title}"
        subtitle_path = SUBTITLE_FOLDER / f"{base_name}.srt"
        summary_path = SUMMARY_FOLDER / f"{base_name}.txt"

        # 使用新的任務佇列系統
        user_ip = get_client_ip()
        queue_manager = get_task_queue()

        # 準備任務資料
        task_data = {
            'audio_file': str(file_path),
            'subtitle_path': str(subtitle_path),
            'summary_path': str(summary_path),
            'title': title or safe_title,
            'filename': safe_filename
        }

        # 將任務加入佇列
        queue_task_id = queue_manager.add_task('upload_media', task_data, priority=5, user_ip=user_ip)

        # 獲取佇列位置
        queue_position = queue_manager.get_user_queue_position(queue_task_id)

        return jsonify({
            'success': True,
            'message': '檔案上傳成功，已加入處理佇列',
            'task_id': queue_task_id,
            'queue_position': queue_position,
            'filename': safe_filename,
            'title': title or safe_title,
            'file_size': file_size,
            'original_task_id': task_id  # 保留原始任務ID作為參考
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'上傳檔案時發生錯誤：{str(e)}'
        }), 500

# --- Task Queue API Routes ---
@app.route('/queue')
def queue_page():
    """任務佇列管理頁面"""
    return render_template('queue.html')

@app.route('/api/queue/status')
def api_get_queue_status():
    """API: 獲取佇列狀態概覽"""
    try:
        queue_manager = get_task_queue()
        status = queue_manager.get_queue_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'獲取佇列狀態失敗: {str(e)}'
        }), 500

@app.route('/api/queue/list')
def api_get_queue_list():
    """API: 獲取任務列表"""
    try:
        queue_manager = get_task_queue()
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))

        # 移除通行碼驗證，允許所有人查看所有任務
        tasks = queue_manager.get_task_list(
            status=status,
            limit=limit,
            user_ip=None  # 不再限制只能查看自己的任務
        )

        return jsonify({
            'success': True,
            'tasks': tasks,
            'has_access': True  # 永遠回傳 True，因為所有人都有查看權限
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'獲取任務列表失敗: {str(e)}'
        }), 500

@app.route('/api/queue/task/<task_id>')
def api_get_task_detail(task_id):
    """API: 獲取任務詳情"""
    try:
        queue_manager = get_task_queue()
        task = queue_manager.get_task(task_id)

        if not task:
            return jsonify({
                'success': False,
                'message': '任務不存在'
            }), 404

        # 移除權限檢查，允許所有人查看任務詳情
        # 新增佇列位置資訊
        if task['status'] == 'queued':
            task['queue_position'] = queue_manager.get_user_queue_position(task_id)

        return jsonify({
            'success': True,
            'task': task
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'獲取任務詳情失敗: {str(e)}'
        }), 500

@app.route('/api/queue/cancel', methods=['POST'])
def api_cancel_queue_task():
    """API: 取消佇列中的任務"""
    try:
        data = request.get_json()
        if not data or 'task_id' not in data:
            return jsonify({
                'success': False,
                'message': '缺少任務ID'
            }), 400

        task_id = data['task_id']
        access_code = data.get('access_code', '').strip()

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        queue_manager = get_task_queue()
        success, message = queue_manager.cancel_task(task_id, access_code)

        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'取消任務失敗: {str(e)}'
        }), 500

@app.route('/api/queue/cleanup', methods=['POST'])
def api_cleanup_queue():
    """API: 清理已完成的任務"""
    try:
        data = request.get_json()
        access_code = data.get('access_code', '').strip() if data else ''
        older_than_days = data.get('older_than_days', 7) if data else 7

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        queue_manager = get_task_queue()
        deleted_count = queue_manager.cleanup_completed_tasks(older_than_days)

        return jsonify({
            'success': True,
            'message': f'已清理 {deleted_count} 個已完成的任務',
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'清理任務失敗: {str(e)}'
        }), 500

@app.route('/api/queue/add', methods=['POST'])
def api_add_queue_task():
    """API: 新增任務到佇列"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '缺少請求資料'
            }), 400

        task_type = data.get('task_type')
        task_data = data.get('data', {})
        priority = data.get('priority', 5)
        access_code = data.get('access_code', '').strip()

        # 檢查必要參數
        if not task_type:
            return jsonify({
                'success': False,
                'message': '缺少任務類型'
            }), 400

        # 檢查通行碼
        system_access_code = get_config("ACCESS_CODE")
        if system_access_code and access_code != system_access_code:
            return jsonify({
                'success': False,
                'message': '通行碼錯誤'
            }), 401

        # 驗證任務類型
        valid_types = ['youtube', 'upload_media', 'upload_subtitle']
        if task_type not in valid_types:
            return jsonify({
                'success': False,
                'message': f'無效的任務類型。支援類型: {", ".join(valid_types)}'
            }), 400

        user_ip = get_client_ip()
        queue_manager = get_task_queue()
        task_id = queue_manager.add_task(task_type, task_data, priority, user_ip)

        # 獲取佇列位置
        queue_position = queue_manager.get_user_queue_position(task_id)

        return jsonify({
            'success': True,
            'message': '任務已加入佇列',
            'task_id': task_id,
            'queue_position': queue_position
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'新增任務失敗: {str(e)}'
        }), 500

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
        cert_file = Path(__file__).parent / 'certs' / 'cert.pem'
        key_file = Path(__file__).parent / 'certs' / 'key.pem'

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

    for folder in [DOWNLOAD_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER, LOG_FOLDER, TRASH_FOLDER, UPLOAD_FOLDER]:
        folder.mkdir(exist_ok=True)

    # 建立回收桶子資料夾
    (TRASH_FOLDER / "summaries").mkdir(exist_ok=True)
    (TRASH_FOLDER / "subtitles").mkdir(exist_ok=True)

    socketio.start_background_task(target=queue_listener, res_queue=results_queue)

    # 啟動新的佇列工作程式（與舊系統並行）
    try:
        from queue_worker import start_queue_worker
        queue_worker = start_queue_worker(
            data_dir=Path(__file__).parent,
            openai_key=get_config("OPENAI_API_KEY")
        )
        print("✅ 新任務佇列工作程式已啟動")
    except Exception as e:
        print(f"⚠️  新任務佇列工作程式啟動失敗: {e}")

    # 保持舊的工作程式以向後兼容
    worker_args = (
        task_queue, results_queue, stop_event,
        str(DOWNLOAD_FOLDER), str(SUMMARY_FOLDER), str(SUBTITLE_FOLDER),
        get_config("OPENAI_API_KEY")
    )
    worker_process = Process(target=background_worker, args=worker_args)
    worker_process.start()

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
        stop_event.set()
        results_queue.put('STOP')
        worker_process.join(timeout=5)
        if worker_process.is_alive(): worker_process.terminate()
        print("程式已完全關閉。")