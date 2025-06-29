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

    def _get_config(self, key, default=None):
        """獲取配置值（與 app.py 中的 get_config 邏輯保持一致）"""
        # 這裡可以實現配置讀取邏輯，或者直接使用環境變數
        return os.getenv(key, default)

    def _send_telegram_notification(self, message):
        """發送 Telegram 通知"""
        bot_token = self._get_config('TELEGRAM_BOT_TOKEN')
        chat_id = self._get_config('TELEGRAM_CHAT_ID')
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

    def _sanitize_filename(self, filename, max_length=80):
        """檔案名稱清理函數（與主程式保持一致）"""
        if not filename:
            return "unknown"

        # 使用與主程式相同的清理邏輯
        # 1. 移除 Windows 禁用字元
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

        # 2. 移除常見特殊符號
        filename = re.sub(r'[\[\]{}()!@#$%^&+=~`]', '_', filename)

        # 3. 移除表情符號和其他 Unicode 符號（保留中文字元）
        filename = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf\w\s\-_.]', '_', filename, flags=re.UNICODE)

        # 4. 處理多重空格和底線
        filename = re.sub(r'\s+', '_', filename)
        filename = re.sub(r'_+', '_', filename)

        # 5. 移除開頭和結尾的特殊字元
        filename = filename.strip('._')

        # 6. 長度限制
        if len(filename.encode('utf-8')) > max_length * 2:
            filename = filename.encode('utf-8')[:max_length].decode('utf-8', errors='ignore')

        return filename if filename else "unknown"

    def _segments_to_srt(self, segments):
        """將 Whisper 片段轉換為 SRT 格式"""
        def format_timestamp(seconds):
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            return f"{int(hours):02}:{int(minutes):02}:{int(secs):02},{int((secs-int(secs))*1000):03}"

        return "\n".join(
            f"{i}\n{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n{segment.text.strip()}\n"
            for i, segment in enumerate(segments, 1)
        )

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

            # 獲取摘要服務
            summary_service = get_summary_service(
                openai_api_key=self.openai_key,
                config_getter=self._get_config
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
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)

            # 配置 yt-dlp
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': str(self.download_folder / '%(title)s.%(ext)s'),
                'noplaylist': True,
            }

            # 下載影片
            with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = title or info.get('title', 'Unknown')
                filename = ydl.prepare_filename(info)

            print(f"[WORKER] Downloaded: {filename}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=50)

            # 處理音訊轉錄
            audio_file = Path(filename)
            if not audio_file.exists():
                raise FileNotFoundError(f"Downloaded file not found: {filename}")

            # 生成輸出檔案路徑
            safe_title = self._sanitize_filename(video_title)
            date_str = datetime.now().strftime('%Y.%m.%d')
            base_name = f"{date_str} - {safe_title}"

            subtitle_path = self.subtitle_folder / f"{base_name}.srt"
            summary_path = self.summary_folder / f"{base_name}.txt"

            # 轉錄音訊
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

            # 發送通知
            notification_msg = f"✅ YouTube 影片處理完成\n標題: {video_title}\n檔案: {base_name}"
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

            # 發送通知
            notification_msg = f"✅ 音訊檔案處理完成\n檔案: {audio_file.name}"
            self._send_telegram_notification(notification_msg)

        except Exception as e:
            error_msg = f"上傳媒體任務處理失敗: {str(e)}"
            print(f"[WORKER] {error_msg}")
            print(f"[WORKER] Error details: {traceback.format_exc()}")
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED, error_message=error_msg
            )

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
            srt_content = self._segments_to_srt(segments_list)

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
                srt_content = self._segments_to_srt(segments_list)

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