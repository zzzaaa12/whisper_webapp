

import os
import sys
import time
import traceback
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
from src.services.email_service import EmailService

class TaskProcessor:
    """
    負責處理各種類型任務的具體邏輯。
    作為 QueueWorker 的子組件，封裝了下載、轉錄、摘要等流程。
    """
    def __init__(self,
                 data_dir: Path,
                 task_queue_manager, # TaskQueue instance
                 whisper_manager_instance, # WhisperModelManager instance
                 summary_service_instance, # SummaryService instance
                 notification_service_instance, # NotificationService instance
                 file_service_instance # FileService instance
                 ):
        self.data_dir = data_dir
        self.download_folder = data_dir / "downloads"
        self.summary_folder = data_dir / "summaries"
        self.subtitle_folder = data_dir / "subtitles"
        self.upload_folder = data_dir / "uploads"

        self.task_queue = task_queue_manager
        self.whisper_manager = whisper_manager_instance
        self.summary_service = summary_service_instance
        self.notification_service = notification_service_instance
        self.file_service = file_service_instance
        self.yt_dlp = yt_dlp
        self.email_service = EmailService()

    def _log_worker_message(self, task_id, message, level='info'):
        # This is a placeholder. In a real app, this would emit to a central log or socket.
        from src.utils.logger_manager import get_logger_manager
        logger_manager = get_logger_manager()
        logger_manager.info(f"[Task {task_id[:8]}] {message}", "task_processor")
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, log_message=message)

    def _should_skip_transcription(self, subtitle_path: Path) -> tuple[bool, str]:
        """檢查是否應該跳過轉錄工作

        Returns:
            tuple: (should_skip, reason)
        """
        if not subtitle_path.exists():
            return False, "字幕檔案不存在"

        try:
            file_size = subtitle_path.stat().st_size
            if file_size <= 500:
                return False, f"字幕檔案過小 ({file_size} bytes)"

            # 檢查檔案內容是否可讀
            content = subtitle_path.read_text(encoding='utf-8')
            if len(content.strip()) == 0:
                return False, "字幕檔案為空"

            return True, f"找到有效字幕檔案 ({file_size} bytes)"

        except Exception as e:
            return False, f"字幕檔案檢查失敗: {str(e)}"

    def _should_skip_summarization(self, summary_path: Path) -> tuple[bool, str]:
        """檢查是否應該跳過摘要生成工作

        Returns:
            tuple: (should_skip, reason)
        """
        if not summary_path.exists():
            return False, "摘要檔案不存在"

        try:
            file_size = summary_path.stat().st_size
            if file_size <= 500:
                return False, f"摘要檔案過小 ({file_size} bytes)"

            # 檢查檔案內容是否可讀
            content = summary_path.read_text(encoding='utf-8')
            if len(content.strip()) == 0:
                return False, "摘要檔案為空"

            return True, f"找到有效摘要檔案 ({file_size} bytes)"

        except Exception as e:
            return False, f"摘要檔案檢查失敗: {str(e)}"


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
        self._log_worker_message(task_id, "開始下載影片...")
        with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        self._log_worker_message(task_id, f"Downloaded: {filename}")
        audio_file = Path(filename)
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=50)
        return audio_file

    def _transcribe_audio(self, audio_file, subtitle_path, task_id):
        """轉錄音訊檔案"""
        if not self.whisper_manager.is_loaded:
            self.whisper_manager.load_model(log_callback=lambda msg, level: self._log_worker_message(task_id, msg, level))

        self._log_worker_message(task_id, f"Transcribing audio: {audio_file}")
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=60)

        try:
            success, segments_list = self.whisper_manager.transcribe_with_fallback(
                str(audio_file),
                log_callback=lambda msg, level: self._log_worker_message(task_id, msg, level)
            )

            if not success:
                raise RuntimeError("轉錄失敗")

            self._log_worker_message(task_id, f"Transcription completed, {len(segments_list)} segments")

            srt_content = segments_to_srt(segments_list)

            subtitle_path.parent.mkdir(exist_ok=True)

            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            self._log_worker_message(task_id, f"Subtitle saved to {subtitle_path}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=80)

        except Exception as e:
            self._log_worker_message(task_id, f"Transcription error: {e}", 'error')
            raise

    def _do_summarize(self, subtitle_content, summary_save_path, task_id, header_info=None):
        """生成摘要（使用統一的摘要服務）"""
        # 獲取摘要服務 - 支援多 AI 提供商
        preferred_ai_provider = self.task_queue.get_task(task_id)
        ai_provider = None
        if preferred_ai_provider and isinstance(preferred_ai_provider, dict):
            ai_provider = preferred_ai_provider.get('data', {}).get('ai_provider')

        # 創建統一的日誌回調
        log_callback = create_log_callback(
            module="task_processor",
            task_id=task_id,
            socketio_callback=lambda msg, level: self._log_worker_message(task_id, msg, level)
        )

        def progress_callback(progress):
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=progress)

        summary_service = self.summary_service # Use the injected instance

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
            self._log_worker_message(task_id, f"Summary generation failed: {result}", 'error')
            raise RuntimeError(f"Summary generation failed: {result}") # Raise to fail task

    def _send_summary_email(self, task_id: str, title: str, summary_path: Path):
        """發送摘要郵件"""
        try:
            if self.email_service.send_summary(title, summary_path):
                self._log_worker_message(task_id, "✉️ 摘要郵件發送成功")
            else:
                self._log_worker_message(task_id, "⚠️ 摘要郵件發送失敗：郵件設定不完整", 'warning')
        except Exception as e:
            self._log_worker_message(task_id, f"❌ 摘要郵件發送失敗：{str(e)}", 'error')

    def _send_task_notification(self, task_id, video_title, sanitized_title, url, summary_path, original_file_name=None):
        notification_msg = ""
        if original_file_name: # Uploaded file
            notification_msg = f"✅ 音訊檔案處理完成\n檔案: {original_file_name}"
        else: # YouTube video
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
                self._log_worker_message(task_id, f"讀取摘要文件失敗: {e}", 'error')
                notification_msg += f"\n\n❌ 摘要生成完成，但讀取失敗: {e}"

        self.notification_service(notification_msg) # Use the injected notification service

    def process_youtube_task(self, task):
        """處理 YouTube 任務"""
        task_id = task.task_id
        data = task.data

        try:
            url = data.get('url')
            title = data.get('title', '')

            if not url:
                raise ValueError("缺少 YouTube URL")

            self._log_worker_message(task_id, f"Processing YouTube URL: {url}")

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
            self.notification_service(f"🎬 開始處理影片\n標題: {video_title}\n上傳者: {uploader}")

            # 準備檔案路徑
            date_str = get_timestamp('date')
            is_auto_task = data.get('auto', False)

            if is_auto_task:
                base_name = f"{video_title}"
                if len(uploader) <= 10:
                    sanitized_title = f"{date_str} - [Auto][{uploader}] " + sanitize_filename(base_name)
                elif uploader == "All-In Podcast":
                    sanitized_title = f"{date_str} - [Auto][All-In] " + sanitize_filename(base_name)
                else:
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
                    self._log_worker_message(task_id, f"Found existing file: {audio_file}")
                    break

            # 檢查是否應該跳過轉錄
            should_skip_transcription, skip_reason = self._should_skip_transcription(subtitle_path)
            if should_skip_transcription:
                self.task_queue.update_task_status(
                    task_id, TaskStatus.PROCESSING, progress=80,
                    log_message="✅ 跳過轉錄，使用現有字幕"
                )
                self._log_worker_message(task_id, f"跳過轉錄: {skip_reason}")
                skip_transcription = True
            else:
                self._log_worker_message(task_id, f"需要轉錄: {skip_reason}")
                skip_transcription = False

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

                # 檢查是否應該跳過摘要生成
                should_skip_summarization, summary_skip_reason = self._should_skip_summarization(summary_path)
                if should_skip_summarization:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=100,
                        log_message="✅ 跳過摘要生成，使用現有摘要"
                    )
                    self._log_worker_message(task_id, f"跳過摘要生成: {summary_skip_reason}")
                else:
                    self._log_worker_message(task_id, f"需要生成摘要: {summary_skip_reason}")
                    self._do_summarize(subtitle_content, summary_path, task_id, header_info={'title': video_title, 'uploader': uploader, 'url': url})

                # 發送摘要郵件（無論是否跳過摘要生成）
                self._send_summary_email(task_id, video_title, summary_path)

            # 更新任務結果
            result = {
                'audio_file': str(audio_file),
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path),
                'title': video_title,
                'url': url
            }

            # 發送完成通知
            self._send_task_notification(task_id, video_title, sanitized_title, url, summary_path)

            return result

        except Exception as e:
            self._log_worker_message(task_id, f"處理 YouTube 任務時發生錯誤：{str(e)}", 'error')
            raise

    def process_upload_media_task(self, task):
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

            self._log_worker_message(task_id, f"Processing uploaded media: {audio_file.name}")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)

            # 發送 Telegram 通知
            self.notification_service(f"🎵 開始處理音訊檔案\n檔案: {title or audio_file.name}")

            # 檢查是否應該跳過轉錄
            should_skip_transcription, skip_reason = self._should_skip_transcription(subtitle_path)
            if should_skip_transcription:
                self.task_queue.update_task_status(
                    task_id, TaskStatus.PROCESSING, progress=60,
                    log_message="✅ 跳過轉錄，使用現有字幕"
                )
                self._log_worker_message(task_id, f"跳過轉錄: {skip_reason}")
            else:
                self._log_worker_message(task_id, f"需要轉錄: {skip_reason}")
                # 轉錄音訊
                self._transcribe_audio(audio_file, subtitle_path, task_id)

            # 生成摘要
            if subtitle_path.exists():
                subtitle_content = subtitle_path.read_text(encoding='utf-8')

                # 檢查是否應該跳過摘要生成
                should_skip_summarization, summary_skip_reason = self._should_skip_summarization(summary_path)
                if should_skip_summarization:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=100,
                        log_message="✅ 跳過摘要生成，使用現有摘要"
                    )
                    self._log_worker_message(task_id, f"跳過摘要生成: {summary_skip_reason}")
                else:
                    self._log_worker_message(task_id, f"需要生成摘要: {summary_skip_reason}")
                    self._do_summarize(subtitle_content, summary_path, task_id, header_info={'filename': audio_file.name, 'title': title})

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
            self._send_task_notification(task_id, None, None, None, summary_path, original_file_name=original_title)

        except Exception as e:
            error_msg = f"處理音訊檔案時發生錯誤: {str(e)}"
            self._log_worker_message(task_id, error_msg, 'error')
            self._log_worker_message(task_id, f"Error details: {traceback.format_exc()}", 'error')
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED,
                error_message=error_msg
            )
            # 發送錯誤通知
            self.notification_service(f"❌ 音訊檔案處理失敗\n檔案: {title or audio_file.name}\n錯誤: {str(e)}")

