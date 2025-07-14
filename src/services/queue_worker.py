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
import yt_dlp

from task_queue import get_task_queue, TaskStatus
from src.config import get_config
from src.services.notification_service import send_telegram_notification
from src.utils.file_sanitizer import sanitize_filename
from src.utils.srt_converter import segments_to_srt
from src.utils.logger_manager import create_log_callback
from src.utils.time_formatter import get_timestamp
from src.services.whisper_manager import get_whisper_manager
from src.services.ai_summary_service import get_summary_service
from src.services.file_service import FileService
from src.services.task_processor import TaskProcessor


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

        # Initialize TaskProcessor
        self.task_processor = TaskProcessor(
            data_dir=data_dir,
            task_queue_manager=self.task_queue,
            whisper_manager_instance=get_whisper_manager(),
            summary_service_instance=get_summary_service(openai_api_key=self.openai_key),
            notification_service_instance=send_telegram_notification,
            file_service_instance=FileService()
        )

        # 工作線程
        self.worker_thread = None
        self.is_running = False
        self.yt_dlp = yt_dlp # Assign yt_dlp here

    # _get_config 已移除，統一使用 utils.get_config

    # _send_telegram_notification 已移除，統一使用 utils.send_telegram_notification



    # _sanitize_filename 已移除，統一使用 utils.sanitize_filename

    # _segments_to_srt 已移除，統一使用 utils.segments_to_srt



    def _do_summarize(self, subtitle_content, summary_save_path, task_id, header_info=None):
        """生成摘要（使用統一的摘要服務）"""
        if not self.openai_key:
            print("[WORKER] OpenAI API key not set, skipping summarization")
            return

        try:
            from ai_summary_service import get_summary_service

            # 創建統一的日誌回調
            log_callback = create_log_callback(
                module="queue_worker",
                task_id=task_id,
                socketio_callback=lambda msg, level: print(f"[WORKER] {msg}")
            )

            def progress_callback(progress):
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=progress)

            # 獲取摘要服務 - 支援多 AI 提供商
            preferred_ai_provider = task_id and self.task_queue.get_task(task_id)
            ai_provider = None
            if preferred_ai_provider and isinstance(preferred_ai_provider, dict):
                ai_provider = preferred_ai_provider.get('data', {}).get('ai_provider')

            summary_service = get_summary_service(
                openai_api_key=self.openai_key,
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

    def _download_youtube_audio(self, url: str, task_id: str, video_title: str) -> Path:
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
        return audio_file

    def _process_youtube_task(self, task):
        """處理 YouTube 任務"""
        task_id = task.task_id
        data = task.data

        try:
            url = data.get('url')
            title = data.get('title', '')

            if not url:
                raise ValueError("缺少 YouTube URL")

            # 移除延遲導入 yt-dlp
            # if not self.yt_dlp:
            #     import yt_dlp
            #     self.yt_dlp = yt_dlp

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
            send_telegram_notification(notification_msg)

            # 準備檔案路徑
            date_str = get_timestamp('date')
            is_auto_task = data.get('auto', False)

            if is_auto_task:
                base_name = f"{video_title}"
                sanitized_title = f"{date_str} - [Auto] " + sanitize_filename(base_name)
            else:
                base_name = f"{date_str} - {video_title}"
                sanitized_title = sanitize_filename(base_name)

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
                audio_file = self._download_youtube_audio(url, task_id, video_title)
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

            send_telegram_notification(notification_msg)

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
            send_telegram_notification(notification_msg)

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
            send_telegram_notification(notification_msg)

        except Exception as e:
            error_msg = f"處理音訊檔案時發生錯誤: {str(e)}"
            print(f"[WORKER] {error_msg}")
            print(f"[WORKER] Error details: {traceback.format_exc()}")
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED,
                error_message=error_msg
            )
            # 發送錯誤通知
            send_telegram_notification(f"❌ 音訊檔案處理失敗\n檔案: {title or audio_file.name}\n錯誤: {str(e)}")

    def _transcribe_audio(self, audio_file, subtitle_path, task_id):
        """轉錄音訊檔案"""
        whisper_manager = get_whisper_manager()
        if not whisper_manager.is_loaded:
            whisper_manager.load_model()

        print(f"[WORKER] Transcribing audio: {audio_file}")
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=60)

        try:
            success, segments_list = whisper_manager.transcribe_with_fallback(str(audio_file))

            if not success:
                raise RuntimeError("轉錄失敗")

            print(f"[WORKER] Transcription completed, {len(segments_list)} segments")

            srt_content = segments_to_srt(segments_list)

            subtitle_path.parent.mkdir(exist_ok=True)

            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            print(f"[WORKER] Subtitle saved to {subtitle_path}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=80)

        except Exception as e:
            print(f"[WORKER] Transcription error: {e}")
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
                    self.task_processor.process_youtube_task(task)
                elif task.task_type == 'upload_media':
                    self.task_processor.process_upload_media_task(task)
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
