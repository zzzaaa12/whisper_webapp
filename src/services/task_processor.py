

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

transcription_task_types = {"youtube", "upload_media"}


def cleanup_original_file(file_path, log_callback=None) -> bool:
    """
    清理原始音訊/影片檔案
    
    Args:
        file_path: 要刪除的檔案路徑 (Path 或 str)
        log_callback: 日誌回調函數
    
    Returns:
        bool: 是否成功刪除
    """
    try:
        # 確保是 Path 物件
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        if log_callback:
            log_callback(f"嘗試清理檔案: {file_path}", 'info')
        
        if file_path and file_path.exists():
            file_size = file_path.stat().st_size
            file_path.unlink()
            if log_callback:
                log_callback(f"✅ 已清理原始檔案: {file_path.name} ({file_size / 1024 / 1024:.2f} MB)", 'info')
            return True
        else:
            if log_callback:
                log_callback(f"檔案不存在，無需清理: {file_path}", 'warning')
    except Exception as e:
        if log_callback:
            log_callback(f"清理原始檔案失敗: {file_path} - {e}", 'warning')
    return False

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
            # 添加 HTTP 相關設定以避免 403 錯誤
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            # 使用 cookies（如果需要）
            'cookiesfrombrowser': None,  # 可以設置為 ('chrome',) 或 ('firefox',) 來使用瀏覽器 cookies
            # 添加重試和超時設定
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 30,
            # 避免被偵測為機器人
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
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
            self._maybe_unload_whisper_after_transcription(task_id, "task completed")

        except Exception as e:
            self._log_worker_message(task_id, f"Transcription error: {e}", 'error')
            self._maybe_unload_whisper_after_transcription(task_id, "task failed")
            raise

    def _is_dynamic_whisper_unload_enabled(self) -> bool:
        return bool(get_config("whisper.dynamic_unload_enabled", False))

    def _has_pending_transcription_tasks(self, exclude_task_id=None) -> bool:
        queued_tasks = self.task_queue.get_task_list(status='queued', limit=None)
        for task in queued_tasks:
            if exclude_task_id and task.get('task_id') == exclude_task_id:
                continue
            if task.get('task_type') in transcription_task_types:
                return True
        return False

    def _maybe_unload_whisper_after_transcription(self, task_id: str, reason: str):
        if not self._is_dynamic_whisper_unload_enabled():
            return

        if not self.whisper_manager.is_loaded:
            return

        if self._has_pending_transcription_tasks(exclude_task_id=task_id):
            self._log_worker_message(task_id, "Keeping Whisper model loaded because more transcription tasks are queued")
            return

        self.whisper_manager.unload_model()
        self._log_worker_message(task_id, f"Whisper model unloaded after transcription ({reason})")

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

    def _send_summary_email(self, task_id: str, title: str, summary_path: Path, channel_name: str = ""):
        """發送摘要郵件"""
        try:
            if self.email_service.send_summary(title, summary_path, channel_name):
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
                #notification_msg += f"\n\n📝 摘要內容：\n{summary_content}"
                notification_msg = f"📝 摘要內容：\n{summary_content}"
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
            user_title = data.get('title', '')
            user_uploader = data.get('uploader', '')

            if not url:
                raise ValueError("缺少 YouTube URL")

            self._log_worker_message(task_id, f"Processing YouTube URL: {url}")

            # 先獲取影片資訊（不下載）
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # 改為 False 以獲取完整信息
                # 添加 HTTP 相關設定以避免 403 錯誤
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                },
                'cookiesfrombrowser': None,
                'retries': 10,
                'socket_timeout': 30,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            }
            with self.yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                auto_video_title = info.get('title', '')
                auto_uploader = info.get('uploader', '')
                duration = info.get('duration', 0)

            # 優先使用用戶提供的metadata，否則使用自動獲取的
            video_title = user_title if user_title else auto_video_title
            uploader = user_uploader if user_uploader else auto_uploader

            # 格式化影片長度
            duration_string = ""
            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    duration_string = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_string = f"{minutes:02d}:{seconds:02d}"

            # 更新任務資料
            self.task_queue.update_task_status(
                task_id, TaskStatus.PROCESSING,
                data_update={'title': video_title, 'uploader': uploader}
            )

            # 獲取佇列位置（在任務開始處理前）
            queue_position = self.task_queue.get_user_queue_position(task_id)

            # 發送 Telegram 通知
            notification_msg = f"🎬 開始處理影片\n標題: {video_title}\n上傳者: {uploader}"
            if queue_position > 0:
                notification_msg += f"\n📍 佇列位置: 第 {queue_position} 位"
            self.notification_service(notification_msg)

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

            # 檢查是否已有相同內容的影片檔案（使用新的檔名比對邏輯）
            from src.utils.filename_matcher import FilenameMatcher

            audio_file = FilenameMatcher.find_existing_audio_file(video_title, self.download_folder)
            skip_transcription = False

            if audio_file:
                self._log_worker_message(task_id, f"Found existing file: {audio_file}")

            # 檢查是否已有相同內容的字幕檔案
            matching_subtitles = FilenameMatcher.find_matching_files(
                f"{sanitized_title}.srt", self.subtitle_folder, ['.srt']
            )

            for subtitle_file in matching_subtitles:
                if subtitle_file.stat().st_size > 500:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=80,
                        log_message="✅ 找到相同內容的字幕快取，跳過轉錄"
                    )
                    self._log_worker_message(task_id, f"找到相同內容的字幕快取: {subtitle_file}")
                    skip_transcription = True
                    # 將找到的字幕檔案複製到目標位置（如果路徑不同）
                    if subtitle_file != subtitle_path:
                        import shutil
                        shutil.copy2(subtitle_file, subtitle_path)
                        self._log_worker_message(task_id, f"複製字幕檔案: {subtitle_file} -> {subtitle_path}")
                    break

            # 如果沒有找到相同內容的字幕，檢查目標路徑是否已有字幕檔案
            if not skip_transcription:
                should_skip_transcription, skip_reason = self._should_skip_transcription(subtitle_path)
                if should_skip_transcription:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=80,
                        log_message="✅ 跳過轉錄，使用目標路徑現有字幕"
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

                # 檢查是否已有相同內容的摘要檔案
                skip_summarization = False
                matching_summaries = FilenameMatcher.find_matching_files(
                    f"{sanitized_title}.txt", self.summary_folder, ['.txt']
                )

                for summary_file in matching_summaries:
                    if summary_file.stat().st_size > 500:
                        self.task_queue.update_task_status(
                            task_id, TaskStatus.PROCESSING, progress=100,
                            log_message="✅ 找到相同內容的摘要快取，跳過摘要生成"
                        )
                        self._log_worker_message(task_id, f"找到相同內容的摘要快取: {summary_file}")
                        skip_summarization = True
                        # 將找到的摘要檔案複製到目標位置（如果路徑不同）
                        if summary_file != summary_path:
                            import shutil
                            shutil.copy2(summary_file, summary_path)
                            self._log_worker_message(task_id, f"複製摘要檔案: {summary_file} -> {summary_path}")
                        break

                # 如果沒有找到相同內容的摘要，檢查目標路徑是否已有摘要檔案
                if not skip_summarization:
                    should_skip_summarization, summary_skip_reason = self._should_skip_summarization(summary_path)
                    if should_skip_summarization:
                        self.task_queue.update_task_status(
                            task_id, TaskStatus.PROCESSING, progress=100,
                            log_message="✅ 跳過摘要生成，使用目標路徑現有摘要"
                        )
                        self._log_worker_message(task_id, f"跳過摘要生成: {summary_skip_reason}")
                    else:
                        self._log_worker_message(task_id, f"需要生成摘要: {summary_skip_reason}")
                        self._do_summarize(subtitle_content, summary_path, task_id, header_info={'title': video_title, 'uploader': uploader, 'url': url, 'duration_string': duration_string})

                # 發送摘要郵件（無論是否跳過摘要生成）
                self._send_summary_email(task_id, video_title, summary_path, uploader)

            # 準備任務結果
            result = {
                'video_title': video_title,
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path),
                'original_file': str(audio_file)
            }

            # 發送完成通知
            self._send_task_notification(task_id, video_title, sanitized_title, url, summary_path)

            # 清理原始音訊檔案
            cleanup_original_file(audio_file, lambda msg, level: self._log_worker_message(task_id, msg, level))

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

            # 獲取佇列位置（在任務開始處理前）
            queue_position = self.task_queue.get_user_queue_position(task_id)

            # 發送 Telegram 通知
            notification_msg = f"🎵 開始處理音訊檔案\n檔案: {title or audio_file.name}"
            if queue_position > 0:
                notification_msg += f"\n📍 佇列位置: 第 {queue_position} 位"
            self.notification_service(notification_msg)

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

            # 準備任務結果
            result = {
                'title': title,
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path) if summary_path.exists() else None,
                'original_file': str(audio_file)
            }

            # 發送完成通知
            original_title = title if title else audio_file.name
            self._send_task_notification(task_id, None, None, None, summary_path, original_file_name=original_title)

            # 清理原始上傳檔案
            cleanup_original_file(audio_file, lambda msg, level: self._log_worker_message(task_id, msg, level))

            return result

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

