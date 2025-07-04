"""
整合式任務佇列工作程式
整合原有的 background_worker 邏輯與新的任務佇列系統
"""

import os
import sys
import time
import traceback
import threading
from datetime import datetime
from pathlib import Path
import uuid
import json
import re
import requests
from urllib.parse import unquote

from task_queue import get_task_queue, TaskStatus

# 統一工具函數導入
from utils import (
    get_config, sanitize_filename, segments_to_srt,
    send_telegram_notification, get_timestamp
)
from whisper_manager import get_whisper_manager, transcribe_audio


class QueueWorker:
    """任務佇列工作程式"""

    def __init__(self, data_dir: Path, openai_key: str = None):
        self.data_dir = data_dir
        self.download_folder = data_dir / "downloads"
        self.summary_folder = data_dir / "summaries"
        self.subtitle_folder = data_dir / "subtitles"
        self.upload_folder = data_dir / "uploads"

        self.openai_key = openai_key
        self.stop_event = threading.Event()
        self.task_queue = get_task_queue()

        # 延遲導入的模組
        self.faster_whisper = None
        self.torch = None
        self.yt_dlp = None
        # 移除OpenAI相關初始化，統一使用ai_summary_service
        # self.openai = None
        self.model = None

        # 工作線程
        self.worker_thread = None
        self.is_running = False

    # _get_config 已移除，統一使用 utils.get_config

    # _send_telegram_notification 已移除，統一使用 utils.send_telegram_notification
    def _send_telegram_notification(self, message):
        """發送 Telegram 通知 - 使用統一工具"""
        return send_telegram_notification(message)

    def _send_log_to_frontend(self, message, task_id=None):
        """發送日誌到前端（簡化版本）"""
        try:
            # 直接在終端輸出
            print(f"[WORKER] {message}")

            # 如果有task_id，透過task_queue發送到前端
            if task_id and self.task_queue:
                try:
                    # 使用update_task_status的log_message參數
                    task_data = self.task_queue.get_task(task_id)
                    if task_data:
                        from task_queue import TaskStatus
                        current_status = TaskStatus(task_data['status'])
                        self.task_queue.update_task_status(
                            task_id, current_status, log_message=message
                        )
                except Exception as e:
                    print(f"[WORKER] Failed to send log via task_queue: {e}")

        except Exception as e:
            print(f"[WORKER] {message}")
            print(f"[WORKER] Log error: {e}")
    # _sanitize_filename 已移除，統一使用 utils.sanitize_filename

    # _segments_to_srt 已移除，統一使用 utils.segments_to_srt

    def _load_model(self):
        """載入 Whisper 模型"""
        if self.model is not None:
            return True

        try:
            # 延遲導入
            if not self.faster_whisper:
                import faster_whisper
                self.faster_whisper = faster_whisper

            if not self.torch:
                import torch
                self.torch = torch

            # 嘗試使用 CUDA，如果失敗則降級到 CPU
            device = "cpu"
            compute = "int8"

            if self.torch.cuda.is_available():
                try:
                    test_tensor = self.torch.zeros(1, device="cuda")
                    del test_tensor
                    device = "cuda"
                    compute = "float16"
                    print(f"[WORKER] Using GPU")
                except Exception:
                    print(f"[WORKER] CUDA failed, using CPU")

            print(f"[WORKER] Loading model with device={device}")
            self.model = self.faster_whisper.WhisperModel(
                "asadfgglie/faster-whisper-large-v3-zh-TW",
                device=device,
                compute_type=compute
            )
            print("[WORKER] Model loaded successfully.")
            return True

        except Exception as e:
            print(f"[WORKER] Could not load model: {e}")
            return False

    def _do_summarize(self, subtitle_content, summary_save_path, task_id, header_info=None):
        """生成摘要（使用統一的摘要服務）"""
        if not self.openai_key:
            print("[WORKER] OpenAI API key not set, skipping summarization")
            return

        try:
            from ai_summary_service import get_summary_service

            # 創建回調函數
            def log_callback(message, level='info'):
                print(f"[WORKER] {message}")

            def progress_callback(progress):
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=progress)

            # 獲取摘要服務 - 支援多 AI 提供商
            preferred_ai_provider = task_id and self.task_queue.get_task(task_id)
            ai_provider = None
            if preferred_ai_provider and isinstance(preferred_ai_provider, dict):
                ai_provider = preferred_ai_provider.get('data', {}).get('ai_provider')

            summary_service = get_summary_service(
                openai_api_key=self.openai_key,
                config_getter=get_config,
                ai_provider=ai_provider
            )

            # 生成並儲存摘要
            success, result = summary_service.generate_and_save_summary(
                subtitle_content=subtitle_content,
                save_path=Path(summary_save_path),
                prompt_type="structured",  # 使用結構化模式
                header_info=header_info,
                progress_callback=progress_callback,
                log_callback=log_callback
            )

            if not success:
                print(f"[WORKER] Summary generation failed: {result}")

        except ImportError:
            # 統一摘要服務不可用，直接報錯
            error_msg = "❌ AI摘要服務模組不可用，請檢查 ai_summary_service.py"
            print(f"[WORKER] {error_msg}")
            raise ImportError(error_msg)

        except Exception as e:
            print(f"[WORKER] Error generating summary: {e}")
            print(f"[WORKER] Summary error details: {traceback.format_exc()}")

    def _process_youtube_task(self, task):
        """處理 YouTube 任務"""
        task_id = task.task_id
        data = task.data

        try:
            url = data.get('url')
            title = data.get('title', '')

            if not url:
                raise ValueError("缺少 YouTube URL")

            # 延遲導入 yt-dlp
            if not self.yt_dlp:
                import yt_dlp
                self.yt_dlp = yt_dlp

            print(f"[WORKER] Processing YouTube URL: {url}")

            # 先獲取影片資訊（不下載）
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True
            }
            with self.yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', '')
                uploader = info.get('uploader', '')

            # 更新任務資料
            self.task_queue.update_task_status(
                task_id, TaskStatus.PROCESSING,
                data_update={'title': video_title, 'uploader': uploader}
            )

            # 發送 Telegram 通知
            notification_msg = f"🎬 開始處理影片\n標題: {video_title}"
            if uploader:
                notification_msg += f"\n上傳者: {uploader}"
            self._send_telegram_notification(notification_msg)

            # 準備檔案路徑
            sanitized_title = sanitize_filename(f"{datetime.now().strftime('%Y.%m.%d')} - {video_title}")
            subtitle_path = self.subtitle_folder / f"{sanitized_title}.srt"
            summary_path = self.summary_folder / f"{sanitized_title}.txt"

            # 檢查是否已有相同檔名的影片
            audio_file = None
            skip_transcription = False
            for file in self.download_folder.glob('*'):
                if video_title in file.stem:
                    audio_file = file
                    print(f"[WORKER] Found existing file: {audio_file}")
                    break

            # 檢查是否已有字幕檔案
            if subtitle_path.exists():
                self.task_queue.update_task_status(
                    task_id, TaskStatus.PROCESSING, progress=60,
                    log_message="✅ 找到字幕快取，跳過轉錄"
                )
                print(f"[WORKER] 找到字幕快取: {subtitle_path}")
                skip_transcription = True

            # 尋找是否已下載相同影片
            if not audio_file:
                # 配置 yt-dlp 下載
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'outtmpl': str(self.download_folder / '%(title)s.%(ext)s'),
                    'noplaylist': True,
                }

                # 下載影片
                self.task_queue.update_task_status(
                    task_id, TaskStatus.PROCESSING, progress=15,
                    log_message="🔄 開始下載影片..."
                )
                print(f"[WORKER] 開始下載影片...")
                with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)

                print(f"[WORKER] Downloaded: {filename}")
                audio_file = Path(filename)
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=50)
            else:
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=50)

            if not audio_file.exists():
                raise FileNotFoundError(f"音訊檔案不存在: {audio_file}")

            # 轉錄音訊（如果還沒有字幕）
            if not skip_transcription:
                self._transcribe_audio(audio_file, subtitle_path, task_id)

            # 生成摘要
            if subtitle_path.exists():
                subtitle_content = subtitle_path.read_text(encoding='utf-8')
                self._do_summarize(subtitle_content, summary_path, task_id)

            # 更新任務結果
            result = {
                'video_title': video_title,
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path) if summary_path.exists() else None,
                'original_file': str(audio_file)
            }

            self.task_queue.update_task_status(
                task_id, TaskStatus.COMPLETED, progress=100, result=result
            )

            # 發送通知（包含摘要內容）
            notification_msg = f"✅ YouTube 影片處理完成\n標題: {video_title}\n檔案: {sanitized_title}\n🔗 網址: {url}"

            # 如果摘要文件存在，添加摘要內容到通知
            if summary_path.exists():
                try:
                    summary_content = summary_path.read_text(encoding='utf-8')
                    # 限制摘要長度，避免telegram訊息過長
                    if len(summary_content) > 3000:
                        summary_content = summary_content[:3000] + "...\n\n[摘要已截斷，完整內容請查看檔案]"
                    notification_msg += f"\n\n📝 摘要內容：\n{summary_content}"
                except Exception as e:
                    print(f"[WORKER] 讀取摘要文件失敗: {e}")
                    notification_msg += f"\n\n❌ 摘要生成完成，但讀取失敗: {e}"

            self._send_telegram_notification(notification_msg)

        except Exception as e:
            error_msg = f"YouTube 任務處理失敗: {str(e)}"
            print(f"[WORKER] {error_msg}")
            print(f"[WORKER] Error details: {traceback.format_exc()}")
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED, error_message=error_msg
            )

    def _process_upload_media_task(self, task):
        """處理上傳媒體任務"""
        task_id = task.task_id
        data = task.data

        try:
            audio_file = Path(data.get('audio_file'))
            subtitle_path = Path(data.get('subtitle_path'))
            summary_path = Path(data.get('summary_path'))
            title = data.get('title', '')

            if not audio_file.exists():
                raise FileNotFoundError(f"音檔不存在: {audio_file}")

            print(f"[WORKER] Processing uploaded media: {audio_file.name}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)

            # 發送 Telegram 通知
            notification_msg = f"🎵 開始處理音訊檔案\n檔案: {title or audio_file.name}"
            self._send_telegram_notification(notification_msg)

            # 轉錄音訊
            self._transcribe_audio(audio_file, subtitle_path, task_id)

            # 生成摘要
            if subtitle_path.exists():
                subtitle_content = subtitle_path.read_text(encoding='utf-8')
                self._do_summarize(subtitle_content, summary_path, task_id)

            # 更新任務結果
            result = {
                'title': title,
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path) if summary_path.exists() else None,
                'original_file': str(audio_file)
            }

            self.task_queue.update_task_status(
                task_id, TaskStatus.COMPLETED, progress=100, result=result
            )

            # 發送完成通知
            original_title = title if title else audio_file.name
            notification_msg = f"✅ 音訊檔案處理完成\n檔案: {original_title}"
            self._send_telegram_notification(notification_msg)

        except Exception as e:
            error_msg = f"處理音訊檔案時發生錯誤: {str(e)}"
            print(f"[WORKER] {error_msg}")
            print(f"[WORKER] Error details: {traceback.format_exc()}")
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED,
                error_message=error_msg
            )
            # 發送錯誤通知
            self._send_telegram_notification(f"❌ 音訊檔案處理失敗\n檔案: {title or audio_file.name}\n錯誤: {str(e)}")

    def _transcribe_audio(self, audio_file, subtitle_path, task_id):
        """轉錄音訊檔案"""
        if not self._load_model():
            raise RuntimeError("無法載入 Whisper 模型")

        print(f"[WORKER] Transcribing audio: {audio_file}")
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=60)

        try:
            # 轉錄音訊
            segments, _ = self.model.transcribe(
                str(audio_file),
                beam_size=1,
                language="zh",
                vad_filter=True
            )

            # 轉換為列表以便計算進度
            segments_list = list(segments)
            print(f"[WORKER] Transcription completed, {len(segments_list)} segments")

            # 生成 SRT 字幕
            srt_content = segments_to_srt(segments_list)

            # 確保目錄存在
            subtitle_path.parent.mkdir(exist_ok=True)

            # 儲存字幕
            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            print(f"[WORKER] Subtitle saved to {subtitle_path}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=80)

        except RuntimeError as e:
            if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                print("[WORKER] CUDA error, retrying with CPU...")
                # 重新載入 CPU 模型
                self.model = self.faster_whisper.WhisperModel(
                    "asadfgglie/faster-whisper-large-v3-zh-TW",
                    device="cpu",
                    compute_type="int8"
                )

                # 重新嘗試轉錄
                segments, _ = self.model.transcribe(
                    str(audio_file),
                    beam_size=1,
                    language="zh",
                    vad_filter=True
                )
                segments_list = list(segments)
                srt_content = segments_to_srt(segments_list)

                with open(subtitle_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                print(f"[WORKER] CPU transcription completed and saved")
            else:
                raise

    def _worker_loop(self):
        """工作程式主迴圈"""
        print("[WORKER] Worker started")

        while not self.stop_event.is_set():
            try:
                # 從佇列取得下一個任務
                task = self.task_queue.get_next_task()

                if task is None:
                    # 沒有任務，等待一秒後繼續
                    time.sleep(1)
                    continue

                print(f"[WORKER] Processing task {task.task_id} ({task.task_type})")

                # 根據任務類型處理
                if task.task_type == 'youtube':
                    self._process_youtube_task(task)
                elif task.task_type == 'upload_media':
                    self._process_upload_media_task(task)
                elif task.task_type == 'upload_subtitle':
                    # 字幕上傳不需要處理，直接標記為完成
                    self.task_queue.update_task_status(
                        task.task_id, TaskStatus.COMPLETED, progress=100
                    )
                else:
                    # 未知任務類型
                    self.task_queue.update_task_status(
                        task.task_id, TaskStatus.FAILED,
                        error_message=f"未知的任務類型: {task.task_type}"
                    )

            except Exception as e:
                print(f"[WORKER] Unexpected error in worker loop: {e}")
                print(f"[WORKER] Error details: {traceback.format_exc()}")
                time.sleep(5)  # 發生錯誤時等待一下

        print("[WORKER] Worker stopped")

    def start(self):
        """啟動工作程式"""
        if self.is_running:
            return

        self.is_running = True
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[WORKER] Worker thread started")

    def stop(self):
        """停止工作程式"""
        if not self.is_running:
            return

        print("[WORKER] Stopping worker...")
        self.stop_event.set()

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=10)

        self.is_running = False
        print("[WORKER] Worker stopped")

    def is_alive(self):
        """檢查工作程式是否運行中"""
        return self.is_running and self.worker_thread and self.worker_thread.is_alive()


# 全域工作程式實例
_worker_instance = None
_worker_lock = threading.Lock()

def get_queue_worker(data_dir: Path = None, openai_key: str = None) -> QueueWorker:
    """獲取佇列工作程式實例（單例模式）"""
    global _worker_instance
    if _worker_instance is None:
        with _worker_lock:
            if _worker_instance is None:
                if data_dir is None:
                    data_dir = Path(__file__).parent
                _worker_instance = QueueWorker(data_dir, openai_key)
    return _worker_instance

def start_queue_worker(data_dir: Path = None, openai_key: str = None):
    """啟動佇列工作程式"""
    worker = get_queue_worker(data_dir, openai_key)
    worker.start()
    return worker

def stop_queue_worker():
    """停止佇列工作程式"""
    global _worker_instance
    if _worker_instance:
        _worker_instance.stop()