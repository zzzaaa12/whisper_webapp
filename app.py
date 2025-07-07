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

from src.config import get_config
from src.services.auth_service import AuthService
from socketio_instance import init_socketio
from task_queue import get_task_queue, TaskStatus

from src.utils.file_sanitizer import sanitize_filename as utils_sanitize_filename
from src.utils.srt_converter import segments_to_srt as utils_segments_to_srt
from src.utils.time_formatter import get_timestamp as utils_get_timestamp
from src.services.notification_service import send_telegram_notification as utils_send_telegram_notification
from whisper_manager import get_whisper_manager, transcribe_audio

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
app.config['SECRET_KEY'] = get_config('SECRET_KEY', os.urandom(24))
socketio = init_socketio(app)
auth_service = AuthService()

BASE_DIR = Path(__file__).parent.resolve()
DOWNLOAD_FOLDER = BASE_DIR / "downloads"
SUMMARY_FOLDER = BASE_DIR / "summaries"
SUBTITLE_FOLDER = BASE_DIR / "subtitles"
LOG_FOLDER = BASE_DIR / "logs"
TRASH_FOLDER = BASE_DIR / "trash"
UPLOAD_FOLDER = BASE_DIR / "uploads"

file_service = FileService()
log_service = LogService(LOG_FOLDER)
gpu_service = GPUService()
socket_service = SocketService(socketio, log_service)
bookmark_service = BookmarkService(BASE_DIR / "bookmarks.json", SUMMARY_FOLDER)
trash_service = TrashService(TRASH_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER)
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


task_queue = Queue()
results_queue = Queue()
stop_event = Event()

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
                socket_service.emit_server_status_update(data.get('is_busy'), data.get('current_task'))
            elif event == 'gpu_status_update':
                socket_service.emit_gpu_status_update(data)
            elif event:
                if sid is None:
                    socket_service.socketio.emit(event, data)
                else:
                    socket_service.socketio.emit(event, data, to=sid)
        except Exception as e:
            print(f"[LISTENER] Error: {e}")






# _actual_transcribe_task 函數已移除，所有語音辨識由 worker process 處理

# do_transcribe 函數已移除，所有語音辨識由 worker process 處理

# 新增統一的任務入列函數




def background_worker(task_q, result_q, stop_evt, download_p, summary_p, subtitle_p, openai_key):
    import faster_whisper, torch, yt_dlp, openai, re
    from pathlib import Path

    # send_telegram_notification 已移至 utils.py
    def send_telegram_notification(message):
        return utils_send_telegram_notification(message)

    DOWNLOAD_FOLDER, SUMMARY_FOLDER, SUBTITLE_FOLDER = Path(download_p), Path(summary_p), Path(subtitle_p)
                    # OpenAI 客戶端已移除，改用統一的 ai_summary_service

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

    task_queue_manager = get_task_queue()

    try:
        url = data.get('audio_url')
        socket_service.log_and_emit(f"收到請求，準備處理網址: {url}", 'info', sid)

        task_id = task_queue_manager.add_task(
            task_type='youtube',
            data={'url': url},
            user_ip=client_ip,
            priority=5
        )

        queue_position = task_queue_manager.get_user_queue_position(task_id)

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
        file_service.ensure_dir(folder)

    # 建立回收桶子資料夾
    file_service.ensure_dir(TRASH_FOLDER / "summaries")
    file_service.ensure_dir(TRASH_FOLDER / "subtitles")

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
