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

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import requests

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
socketio = SocketIO(app, async_mode='threading')

# 安全性增強：設定安全標頭
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# --- Global Definitions ---
BASE_DIR = Path(__file__).parent.resolve()
DOWNLOAD_FOLDER = BASE_DIR / "downloads"
SUMMARY_FOLDER = BASE_DIR / "summaries"
SUBTITLE_FOLDER = BASE_DIR / "subtitles"
LOG_FOLDER = BASE_DIR / "logs"  # 新增日誌資料夾
TRASH_FOLDER = BASE_DIR / "trash"  # 新增回收桶資料夾
TRASH_METADATA_FILE = TRASH_FOLDER / "metadata.json"  # 回收桶記錄檔案

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
    try:
        log_file = LOG_FOLDER / f"session_{sid}.log"
        timestamp = datetime.now().strftime('%m/%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Error saving log: {e}")

def get_session_logs(sid):
    """獲取指定 session 的日誌記錄"""
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
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def is_ip_blocked(ip):
    """檢查 IP 是否被封鎖"""
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
    with attempts_lock:
        if ip in LOGIN_ATTEMPTS:
            del LOGIN_ATTEMPTS[ip]

def get_remaining_attempts(ip):
    """獲取剩餘嘗試次數"""
    with attempts_lock:
        if ip not in LOGIN_ATTEMPTS:
            return MAX_ATTEMPTS
        return max(0, MAX_ATTEMPTS - LOGIN_ATTEMPTS[ip]['count'])

def get_block_remaining_time(ip):
    """獲取封鎖剩餘時間（秒）"""
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
                'last_updated': current_time.strftime('%Y-%m-%d %H:%M:%S')
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

def sanitize_filename(filename, max_length=80):
    """清理字符串以成為有效的檔案名稱，處理中文和特殊字元"""
    if not filename:
        return "unknown"

    # 保存原始檔名用於 debug
    original = filename

    # 1. 移除 Windows 禁用字元
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

    # 2. 移除常見特殊符號（但保留中文、數字、字母）
    filename = re.sub(r'[\[\]{}()!@#$%^&+=~`]', '_', filename)

    # 3. 移除表情符號和其他 Unicode 符號（保留中文字元）
    # 保留：中文字元(CJK)、字母、數字、空格、連字符、底線、點
    filename = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf\w\s\-_.]', '_', filename, flags=re.UNICODE)

    # 4. 處理多重空格
    filename = re.sub(r'\s+', '_', filename)

    # 5. 處理多重底線
    filename = re.sub(r'_+', '_', filename)

    # 6. 移除開頭和結尾的特殊字元
    filename = filename.strip('._')

    # 7. 長度處理（考慮中文字元）
    if len(filename.encode('utf-8')) > max_length * 2:  # 中文字元約佔 2-3 bytes
        if max_length > 20:
            # 智能截斷：保留前 60% 和後面部分
            keep_start = int(max_length * 0.6)
            keep_end = max_length - keep_start - 3

            # 確保不會在中文字元中間截斷
            safe_start = filename[:keep_start].encode('utf-8')[:keep_start*2].decode('utf-8', errors='ignore')
            safe_end = filename[-keep_end:].encode('utf-8')[-keep_end*2:].decode('utf-8', errors='ignore') if keep_end > 0 else ""

            filename = safe_start + "..." + safe_end
        else:
            # 簡單截斷
            filename = filename.encode('utf-8')[:max_length].decode('utf-8', errors='ignore')

    # 8. 最終檢查
    result = filename if filename else "unknown"

    # Debug 輸出（僅在有變化時）
    if result != original:
        print(f"[SANITIZE] '{original}' -> '{result}'")

    return result

def whisper_segments_to_srt(segments):
    """Converts whisper segments to an SRT formatted string."""
    def format_timestamp(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
    srt_lines = []
    for idx, segment in enumerate(segments, 1):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
    return "\n".join(srt_lines)

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
                socketio.emit(event, data, to=sid)
        except Exception as e:
            print(f"[LISTENER] Error: {e}")



# --- Core Processing Logic ---
def do_summarize(subtitle_content, summary_save_path, sid):
    """Performs summarization using OpenAI API."""
    try:
        global openai
        if not openai:
            import openai as o
            openai = o

        api_key = get_config("OPENAI_API_KEY")
        if not api_key:
            log_and_emit("❌ 錯誤：找不到 OPENAI_API_KEY 環境變數。", 'error', sid)
            return

        log_and_emit("▶️ 開始進行 AI 摘要...", 'info', sid)
        client = openai.OpenAI(api_key=api_key)
        prompt = "請將以下字幕提到的每一個重點，做條列式的摘要整理：\n" + subtitle_content

        max_tokens = int(get_config("OPENAI_MAX_TOKENS", 10000))
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "你是一個專業的摘要助手。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.5
        )
        summary_content = response.choices[0].message.content
        summary = summary_content.strip() if summary_content else ""

        if summary:
            log_and_emit(f"✅ AI 摘要完成。", 'success', sid)
            with open(summary_save_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            log_and_emit(f"摘要已儲存至: {summary_save_path}", 'info', sid)
            log_and_emit(f"---摘要內容---\n{summary}", 'info', sid)
        else:
            log_and_emit("⚠️ AI 未回傳有效摘要。", 'warning', sid)

    except Exception as e:
        log_and_emit(f"❌ AI 摘要失敗: {e}", 'error', sid)
        traceback.print_exc()

# _actual_transcribe_task 函數已移除，所有語音辨識由 worker process 處理

# do_transcribe 函數已移除，所有語音辨識由 worker process 處理

# 新增統一的任務入列函數



# --- Background Worker ---
def background_worker(task_q, result_q, stop_evt, download_p, summary_p, subtitle_p, openai_key):
    import faster_whisper, torch, yt_dlp, openai, re
    from pathlib import Path

    def send_telegram_notification(message):
        bot_token = get_config('TELEGRAM_BOT_TOKEN')
        chat_id = get_config('TELEGRAM_CHAT_ID')
        if not bot_token or not chat_id:
            print("[WORKER] Telegram credentials not set. Skipping notification.")
            return

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        try:
            response = requests.post(api_url, data=payload, timeout=5)
            if response.status_code != 200:
                print(f"[WORKER] Error sending Telegram message: {response.text}")
        except Exception as e:
            print(f"[WORKER] Exception while sending Telegram message: {e}")

    DOWNLOAD_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER = Path(download_p), Path(summary_p), Path(subtitle_p)
    client = openai.OpenAI(api_key=openai_key) if openai_key else None

    def worker_emit(event, data, sid): result_q.put({'event': event, 'data': data, 'sid': sid})
    def worker_update_state(is_busy, task_desc): result_q.put({'event': 'update_server_state', 'data': {'is_busy': is_busy, 'current_task': task_desc}})
    def sanitize_filename(f, ml=80):
        """Worker 中的檔案名稱清理函數（與主程式保持一致）"""
        if not f: return "unknown"

        # 使用與主程式相同的清理邏輯
        # 1. 移除 Windows 禁用字元
        f = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', f)

        # 2. 移除常見特殊符號
        f = re.sub(r'[\[\]{}()!@#$%^&+=~`]', '_', f)

        # 3. 移除表情符號和其他 Unicode 符號（保留中文字元）
        f = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf\w\s\-_.]', '_', f, flags=re.UNICODE)

        # 4. 處理多重空格和底線
        f = re.sub(r'\s+', '_', f)
        f = re.sub(r'_+', '_', f)

        # 5. 移除開頭和結尾的特殊字元
        f = f.strip('._')

        # 6. 長度限制（簡化版）
        if len(f.encode('utf-8')) > ml * 2:
            f = f.encode('utf-8')[:ml].decode('utf-8', errors='ignore')

        return f if f else "unknown"
    def segments_to_srt(segs):
        def fmt_ts(s):
            h, r = divmod(s, 3600)
            m, s = divmod(r, 60)
            return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s-int(s))*1000):03}"
        return "\n".join(f"{i}\n{fmt_ts(s.start)} --> {fmt_ts(s.end)}\n{s.text.strip()}\n" for i, s in enumerate(segs, 1))

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
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

                if not (sid and audio_file and subtitle_path and summary_path):
                    print("[WORKER] DEBUG: 任務資料不完整，跳過")
                    continue

                # 設定目前任務
                with task_lock:
                    current_task_sid = sid

                worker_emit('update_log', {'log': "工作程序已接收音訊檔案任務...", 'type': 'info'}, sid)
                worker_update_state(True, f"處理音訊檔案: {Path(audio_file).name[:40]}...")

                try:
                    # 檢查是否被取消
                    with task_lock:
                        if current_task_sid != sid:
                            worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                            continue

                    # 檢查音檔是否存在
                    if not Path(audio_file).exists():
                        worker_emit('update_log', {'log': f"❌ 音檔不存在: {audio_file}", 'type': 'error'}, sid)
                        continue

                    # 檢查音檔大小
                    file_size = Path(audio_file).stat().st_size
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
                    Path(subtitle_path).write_text(srt_content, encoding='utf-8')
                    worker_emit('update_log', {'log': "📝 字幕已儲存", 'type': 'info'}, sid)

                    if client and srt_content:
                        # 檢查是否被取消
                        with task_lock:
                            if current_task_sid != sid:
                                worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                                continue

                        worker_emit('update_log', {'log': "▶️ AI 摘要中...", 'type': 'info'}, sid)
                        prompt = "請將以下字幕內容的每一個細節都做條列式的摘要整理：\n" + srt_content
                        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": prompt}])
                        summary = resp.choices[0].message.content if resp.choices else "AI未回傳摘要"

                        # 在摘要前面加上檔案資訊
                        file_info_header = (
                            f"檔案：{Path(audio_file).name}\n"
                            f"處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"{'='*50}\n\n"
                        )
                        full_summary = file_info_header + summary

                        Path(summary_path).write_text(full_summary, encoding='utf-8')
                        worker_emit('update_log', {'log': "✅ AI 摘要完成", 'type': 'success'}, sid)
                        worker_emit('update_log', {'log': f"---\n{full_summary}", 'type': 'info'}, sid)

                        # --- Send summary notification to Telegram ---
                        tg_message = (
                            f"✅ *摘要完成:*\n\n"
                            f"📄 *檔案:* `{Path(audio_file).name}`\n\n"
                            f"📝 *完整摘要:*\n`{summary}`"
                        )
                        send_telegram_notification(tg_message)
                        # ---------------------------------------------

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
                        if current_task_sid == sid:
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
                        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl: info = ydl.extract_info(url, download=False)

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

                        today_str = datetime.now().strftime('%Y.%m.%d')
                        base_fn = f"{today_str} - {sanitize_filename(info.get('uploader'),30)}-{sanitize_filename(info.get('title'),50)}"
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

                        if client and srt_content:
                            # 檢查是否被取消
                            with task_lock:
                                if current_task_sid != sid:
                                    worker_emit('update_log', {'log': "🛑 任務已被取消", 'type': 'info'}, sid)
                                    continue

                            worker_emit('update_log', {'log': "▶️ AI 摘要中...", 'type': 'info'}, sid)
                            prompt = "請將以下字幕內容的每一個細節都做條列式的摘要整理：\n" + srt_content
                            resp = client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": prompt}])
                            summary = resp.choices[0].message.content if resp.choices else "AI未回傳摘要"

                            # 在摘要前面加上影片資訊
                            video_info_header = (
                                f"頻道：{info.get('uploader', '未知頻道')}\n"
                                f"主題：{info.get('title', '未知標題')}\n"
                                f"網址：{info.get('webpage_url', url)}\n"
                                f"{'='*50}\n\n"
                            )
                            full_summary = video_info_header + summary

                            summary_path.write_text(full_summary, encoding='utf-8')
                            worker_emit('update_log', {'log': "✅ AI 摘要完成", 'type': 'success'}, sid)
                            worker_emit('update_log', {'log': f"---\n{full_summary}", 'type': 'info'}, sid)

                            # --- Send summary notification to Telegram ---
                            # 發送完整摘要而不是只發送預覽
                            tg_message = (
                                f"✅ *摘要完成:*\n\n"
                                f"📄 *標題:* `{info.get('title', 'N/A')}`\n\n"
                                f"📝 *完整摘要:*\n`{summary}`"
                            )
                            send_telegram_notification(tg_message)
                            # ---------------------------------------------

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
                        import re

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

    with state_lock:
        if SERVER_STATE['is_busy']: log_and_emit("⏳ 伺服器忙碌中，您的任務已加入佇列。", 'warning', sid)
        else: log_and_emit('✅ 請求已接收，準備處理...', 'success', sid)

    task_queue.put({'sid': sid, 'audio_url': data.get('audio_url')})

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
    return render_template('summary_detail.html', title=safe_path.stem, content=content)

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
        import re
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

        # 檢查伺服器狀態
        with state_lock:
            is_busy = SERVER_STATE['is_busy']
            current_task = SERVER_STATE['current_task']

        if is_busy:
            return jsonify({
                'status': 'busy',
                'message': f'伺服器忙碌中：{current_task}',
                'current_task': current_task
            }), 200

        # 伺服器空閒，開始處理
        # 生成唯一的任務 ID
        import uuid
        task_id = str(uuid.uuid4())

        # 將任務加入佇列（使用特殊的 API session ID）
        api_sid = f"api_{task_id}"
        task_queue.put({
            'sid': api_sid,
            'audio_url': youtube_url
        })

        return jsonify({
            'status': 'processing',
            'message': '任務已加入佇列，開始處理',
            'task_id': task_id,
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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        safe_name = sanitize_filename(file_path.name)
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
            restore_path = SUMMARY_FOLDER / sanitize_filename(record['original_name'])
        elif record['file_type'] == 'subtitle':
            restore_path = SUBTITLE_FOLDER / sanitize_filename(record['original_name'])
        else:
            return False, "不支援的檔案類型"

        # 檢查目標位置是否已有檔案
        if restore_path.exists():
            # 如果檔案已存在，添加時間戳
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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
        safe_filename = sanitize_filename(filename)
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

    print("🚀 繼續啟動系統...")

    for folder in [DOWNLOAD_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER, LOG_FOLDER, TRASH_FOLDER]:
        folder.mkdir(exist_ok=True)

    # 建立回收桶子資料夾
    (TRASH_FOLDER / "summaries").mkdir(exist_ok=True)
    (TRASH_FOLDER / "subtitles").mkdir(exist_ok=True)

    socketio.start_background_task(target=queue_listener, res_queue=results_queue)

    worker_args = (
        task_queue, results_queue, stop_event,
        str(DOWNLOAD_FOLDER), str(SUMMARY_FOLDER), str(SUBTITLE_FOLDER),
        get_config("OPENAI_API_KEY")
    )
    worker_process = Process(target=background_worker, args=worker_args)
    worker_process.start()

    print("主伺服器啟動，請在瀏覽器中開啟 http://127.0.0.1:5000")

    try:
        socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False)
    finally:
        print("主伺服器準備關閉...")
        stop_event.set()
        results_queue.put('STOP')
        worker_process.join(timeout=5)
        if worker_process.is_alive(): worker_process.terminate()
        print("程式已完全關閉。")