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
from src.utils.logger_manager import create_log_callback, get_logger_manager
from src.utils.time_formatter import get_timestamp
from src.services.whisper_manager import get_whisper_manager
from src.services.ai_summary_service import get_summary_service
from src.services.file_service import FileService
from src.services.task_processor import TaskProcessor
from src.services.youtube_subtitle_extractor import get_youtube_subtitle_extractor
from src.services.email_service import EmailService

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
        self.logger_manager = get_logger_manager()

        # Initialize TaskProcessor
        self.task_processor = TaskProcessor(
            data_dir=data_dir,
            task_queue_manager=self.task_queue,
            whisper_manager_instance=get_whisper_manager(),
            summary_service_instance=get_summary_service(openai_api_key=self.openai_key),
            notification_service_instance=send_telegram_notification,
            file_service_instance=FileService()
        )

        # Initialize YouTube Subtitle Extractor
        self.subtitle_extractor = get_youtube_subtitle_extractor()

        # Initialize Email Service
        self.email_service = EmailService()

        # 工作線程
        self.worker_thread = None
        self.is_running = False
        self.yt_dlp = yt_dlp # Assign yt_dlp here

    def _emit_log_to_frontend(self, task_id: str, message: str, level: str = 'info'):
        """發送日誌到前端"""
        try:
            from src.services.socketio_instance import emit_log
            # 只使用 emit_log 發送日誌，避免重複
            emit_log(message, level, task_id)
        except Exception as e:
            self.logger_manager.error(f"[Task:{task_id[:8]}] 發送日誌到前端失敗: {e}", "queue_worker")

    def _send_summary_email(self, task_id: str, title: str, summary_path: Path, channel_name: str = ""):
        """發送摘要郵件"""
        try:
            if self.email_service.send_summary(title, summary_path, channel_name):
                email_success_msg = "✉️ 摘要郵件發送成功"
                self.logger_manager.info(f"[Task:{task_id[:8]}] {email_success_msg}", "queue_worker")
                self._emit_log_to_frontend(task_id, email_success_msg, 'success')
            else:
                email_fail_msg = "❌ 摘要郵件發送失敗（設定不完整或發送錯誤）"
                self.logger_manager.warning(f"[Task:{task_id[:8]}] {email_fail_msg}", "queue_worker")
                self._emit_log_to_frontend(task_id, email_fail_msg, 'warning')
        except Exception as e:
            email_error_msg = f"❌ 摘要郵件發送異常: {str(e)}"
            self.logger_manager.error(f"[Task:{task_id[:8]}] {email_error_msg}", "queue_worker")
            self._emit_log_to_frontend(task_id, email_error_msg, 'error')

    # _get_config 已移除，統一使用 utils.get_config

    # _send_telegram_notification 已移除，統一使用 utils.send_telegram_notification



    # _sanitize_filename 已移除，統一使用 utils.sanitize_filename

    # _segments_to_srt 已移除，統一使用 utils.segments_to_srt



    def _do_summarize(self, subtitle_content, summary_save_path, task_id, header_info=None):
        """生成摘要（使用統一的摘要服務）"""
        if not self.openai_key:
            no_key_msg = "⚠️ 未設定 OpenAI API Key，跳過摘要生成"
            self.logger_manager.warning("OpenAI API key not set, skipping summarization", "queue_worker")
            self._emit_log_to_frontend(task_id, no_key_msg, 'warning')
            return

        try:
            # 創建自定義的日誌回調，只發送重要訊息到前端
            def custom_log_callback(message: str, level: str = 'info'):
                # 記錄到後端日誌
                self.logger_manager.info(f"[Task:{task_id[:8]}] {message}", "queue_worker")
                # 只發送特定的重要訊息到前端
                if any(keyword in message for keyword in ['開始生成', '使用模型', '生成完成', '已儲存']):
                    self._emit_log_to_frontend(task_id, message, level)

            log_callback = custom_log_callback

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

            if success:
                summary_complete_msg = "✅ AI 摘要生成完成"
                self._emit_log_to_frontend(task_id, summary_complete_msg, 'success')
            else:
                summary_error_msg = f"❌ 摘要生成失敗: {result}"
                self.logger_manager.error(f"Summary generation failed: {result}", "queue_worker")
                self._emit_log_to_frontend(task_id, summary_error_msg, 'error')

        except Exception as e:
            error_msg = f"❌ 摘要生成過程發生錯誤: {str(e)}"
            self.logger_manager.error(f"Error generating summary: {e}", "queue_worker")
            self.logger_manager.error(f"Summary error details: {traceback.format_exc()}", "queue_worker")
            self._emit_log_to_frontend(task_id, error_msg, 'error')

    def _download_youtube_audio(self, url: str, task_id: str, video_title: str) -> Path:
        # 清理影片標題，避免 Windows 檔名禁用字元（:, !, ?, *, <, >, |, \, /, "）
        safe_title = sanitize_filename(video_title)

        # 配置 yt-dlp 下載（使用清理後的標題）
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best[height<=720]/best',
            'outtmpl': str(self.download_folder / f'{safe_title}.%(ext)s'),
            'noplaylist': True,
            'extract_flat': False,
            'writeinfojson': False,
            'ignoreerrors': False,
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
        download_msg = "🔄 開始下載影片..."
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=15)
        self._emit_log_to_frontend(task_id, download_msg)
        self.logger_manager.info("開始下載影片...", "queue_worker")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    # 如果是格式問題，嘗試更簡單的格式
                    if "format" in str(e).lower() or "not available" in str(e).lower():
                        ydl_opts['format'] = 'best/worst' if attempt == 0 else 'worst'
                        retry_msg = f"🔄 格式不可用，重試第 {attempt + 1} 次..."
                        self._emit_log_to_frontend(task_id, retry_msg)
                        self.logger_manager.info(f"Retrying with different format: {ydl_opts['format']}", "queue_worker")
                        continue
                    else:
                        raise
                else:
                    raise

        download_complete_msg = "✅ 影片下載完成"
        self.logger_manager.info(f"Downloaded: {filename}", "queue_worker")
        self._emit_log_to_frontend(task_id, download_complete_msg, 'success')

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

            self.logger_manager.info(f"Processing YouTube URL: {url}", "queue_worker")

            # 先獲取影片資訊（不下載）
            self._emit_log_to_frontend(task_id, "📋 獲取影片資訊...")
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # 改為 False 以獲取完整資訊
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
                video_title = info.get('title', '')
                uploader = info.get('uploader', '')
                duration = info.get('duration', 0)
                view_count = info.get('view_count', 0)
                upload_date = info.get('upload_date', '')
                description = info.get('description', '')
                thumbnail = info.get('thumbnail', '')

            # 更新任務資料，包含完整的影片資訊
            video_info_update = {
                'title': video_title,
                'uploader': uploader,
                'duration': duration,
                'view_count': view_count,
                'upload_date': upload_date,
                'description': description,
                'thumbnail': thumbnail
            }
            self.task_queue.update_task_status(
                task_id, TaskStatus.PROCESSING,
                data_update=video_info_update
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

            # 檢查是否已有相同內容的影片檔案（使用新的檔名比對邏輯）
            from src.utils.filename_matcher import FilenameMatcher

            audio_file = FilenameMatcher.find_existing_audio_file(video_title, self.download_folder)
            skip_transcription = False

            if audio_file:
                self.logger_manager.info(f"Found existing file: {audio_file}", "queue_worker")

            # 檢查是否已有相同內容的字幕檔案
            matching_subtitles = FilenameMatcher.find_matching_files(
                f"{sanitized_title}.srt", self.subtitle_folder, ['.srt']
            )

            for subtitle_file in matching_subtitles:
                if subtitle_file.stat().st_size > 500:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=60,
                        log_message="✅ 找到相同內容的字幕快取，跳過轉錄"
                    )
                    self.logger_manager.info(f"找到相同內容的字幕快取: {subtitle_file}", "queue_worker")
                    skip_transcription = True
                    # 將找到的字幕檔案複製到目標位置（如果路徑不同）
                    if subtitle_file != subtitle_path:
                        import shutil
                        shutil.copy2(subtitle_file, subtitle_path)
                        self.logger_manager.info(f"複製字幕檔案: {subtitle_file} -> {subtitle_path}", "queue_worker")
                    break

            # 如果沒有找到相同內容的字幕，檢查目標路徑是否已有字幕檔案
            if not skip_transcription and subtitle_path.exists():
                if subtitle_path.stat().st_size > 500:
                    self.task_queue.update_task_status(
                        task_id, TaskStatus.PROCESSING, progress=60,
                        log_message="✅ 找到目標路徑字幕檔案，跳過轉錄"
                    )
                    self.logger_manager.info(f"找到目標路徑字幕檔案: {subtitle_path}", "queue_worker")
                    skip_transcription = True

            # 🆕 嘗試擷取 YouTube 原生字幕（如果還沒有字幕）
            if not skip_transcription:
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=25)
                self._emit_log_to_frontend(task_id, "🔍 檢查 YouTube 原生字幕...")

                subtitle_result = self.subtitle_extractor.extract_subtitles(url)

                if subtitle_result['success']:
                    quality_score = subtitle_result['quality_score']
                    source = subtitle_result['source']
                    language = subtitle_result['language']

                    log_msg = f"📝 找到 {language} 字幕 (來源: {source}, 品質: {quality_score}/10)"
                    self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=35)
                    self._emit_log_to_frontend(task_id, log_msg)

                    # 判斷是否使用擷取的字幕
                    if self.subtitle_extractor.should_use_subtitle(quality_score, source):
                        # 轉換為標準 SRT 格式並儲存
                        srt_content = self.subtitle_extractor.convert_to_standard_srt(
                            subtitle_result['content']
                        )

                        subtitle_path.parent.mkdir(exist_ok=True)
                        subtitle_path.write_text(srt_content, encoding='utf-8')

                        skip_transcription = True

                        success_msg = f"✅ 使用 YouTube {language} 字幕 (品質: {quality_score}/10)"
                        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=60)
                        self._emit_log_to_frontend(task_id, success_msg)

                        self.logger_manager.info(
                            f"使用 YouTube 字幕: {language} ({source}), 品質: {quality_score}",
                            "queue_worker"
                        )
                    else:
                        warning_msg = f"⚠️ 字幕品質不佳 ({quality_score}/10)，將使用語音轉錄"
                        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=30)
                        self._emit_log_to_frontend(task_id, warning_msg)
                else:
                    info_msg = "ℹ️ 未找到可用字幕，將使用語音轉錄"
                    self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=30)
                    self._emit_log_to_frontend(task_id, info_msg)

            # 只有在需要轉錄時才下載影片
            if not skip_transcription:
                # 尋找是否已下載相同影片
                if not audio_file:
                    audio_file = self._download_youtube_audio(url, task_id, video_title)
                else:
                    self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=50)

                if not audio_file.exists():
                    raise FileNotFoundError(f"音訊檔案不存在: {audio_file}")

                # 轉錄音訊
                self._transcribe_audio(audio_file, subtitle_path, task_id)
            else:
                # 已有字幕，跳過下載和轉錄
                skip_msg = "⚡ 使用字幕，跳過影片下載和轉錄"
                self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=70)
                self._emit_log_to_frontend(task_id, skip_msg)

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
                        cache_msg = f"✅ 找到相同內容的摘要快取，跳過摘要生成"
                        self.logger_manager.info(f"找到相同內容的摘要快取: {summary_file}", "queue_worker")
                        self._emit_log_to_frontend(task_id, cache_msg)
                        skip_summarization = True
                        # 將找到的摘要檔案複製到目標位置（如果路徑不同）
                        if summary_file != summary_path:
                            import shutil
                            shutil.copy2(summary_file, summary_path)
                            self.logger_manager.info(f"複製摘要檔案: {summary_file} -> {summary_path}", "queue_worker")
                        break

                # 如果沒有找到相同內容的摘要，才生成新摘要
                if not skip_summarization:
                    summary_msg = "🤖 開始生成 AI 摘要..."
                    self._emit_log_to_frontend(task_id, summary_msg)

                    # 準備影片資訊作為摘要標頭
                    header_info = {
                        'title': video_title,
                        'uploader': uploader,
                        'duration': duration,
                        'view_count': view_count,
                        'upload_date': upload_date,
                        'url': url
                    }

                    self._do_summarize(subtitle_content, summary_path, task_id, header_info)

            # 更新任務結果
            result = {
                'video_title': video_title,
                'subtitle_file': str(subtitle_path),
                'summary_file': str(summary_path) if summary_path.exists() else None,
                'original_file': str(audio_file) if audio_file else None,
                'used_subtitle_extraction': skip_transcription  # 標記是否使用了字幕擷取
            }

            # 發送完成日誌到前端
            processing_method = "字幕擷取" if skip_transcription else "語音轉錄"
            completion_msg = f"✅ YouTube 影片處理完成 ({processing_method})"
            self._emit_log_to_frontend(task_id, completion_msg, 'success')

            self.task_queue.update_task_status(
                task_id, TaskStatus.COMPLETED, progress=100, result=result
            )

            # 發送通知（包含摘要內容）
            processing_method = "📝 字幕擷取" if skip_transcription else "🎤 語音轉錄"
            notification_msg = f"✅ YouTube 影片處理完成 ({processing_method})\n標題: {video_title}\n檔案: {sanitized_title}\n🔗 網址: {url}"

            # 如果摘要文件存在，添加摘要內容到通知
            if summary_path.exists():
                try:
                    summary_content = summary_path.read_text(encoding='utf-8')
                    # 限制摘要長度，避免telegram訊息過長
                    if len(summary_content) > 3000:
                        summary_content = summary_content[:3000] + "...\n\n[摘要已截斷，完整內容請查看檔案]"
                    notification_msg = f"📝 摘要內容：\n{summary_content}"
                except Exception as e:
                    self.logger_manager.error(f"讀取摘要文件失敗: {e}", "queue_worker")
                    notification_msg += f"\n\n❌ 摘要生成完成，但讀取失敗: {e}"

            send_telegram_notification(notification_msg)

            # 發送摘要郵件（如果摘要存在）
            if summary_path.exists():
                self._send_summary_email(task_id, video_title, summary_path, uploader)

        except Exception as e:
            error_msg = f"YouTube 任務處理失敗: {str(e)}"
            self.logger_manager.error(error_msg, "queue_worker")
            self.logger_manager.error(f"Error details: {traceback.format_exc()}", "queue_worker")
            self.task_queue.update_task_status(
                task_id, TaskStatus.FAILED, error_message=error_msg
            )

            # 發送錯誤通知
            try:
                # 嘗試獲取影片標題，如果失敗則使用URL
                video_title = data.get('title', url if 'url' in locals() else '未知影片')
                error_notification = f"❌ YouTube 影片處理失敗\n標題: {video_title}\n錯誤: {str(e)}"
                send_telegram_notification(error_notification)
            except Exception as notify_error:
                self.logger_manager.error(f"發送錯誤通知失敗: {notify_error}", "queue_worker")

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

            self.logger_manager.info(f"Processing uploaded media: {audio_file.name}", "queue_worker")
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=10)

            # 發送 Telegram 通知
            notification_msg = f"🎵 開始處理音訊檔案\n檔案: {title or audio_file.name}"
            send_telegram_notification(notification_msg)

            # 轉錄音訊
            self._transcribe_audio(audio_file, subtitle_path, task_id)

            # 生成摘要
            if subtitle_path.exists():
                subtitle_content = subtitle_path.read_text(encoding='utf-8')

                # 檢查是否已有相同內容的摘要檔案
                skip_summarization = False
                matching_summaries = FilenameMatcher.find_matching_files(
                    summary_path.name, self.summary_folder, ['.txt']
                )

                for summary_file in matching_summaries:
                    if summary_file.stat().st_size > 500:
                        self.logger_manager.info(f"找到相同內容的摘要快取: {summary_file}", "queue_worker")
                        skip_summarization = True
                        # 將找到的摘要檔案複製到目標位置（如果路徑不同）
                        if summary_file != summary_path:
                            import shutil
                            shutil.copy2(summary_file, summary_path)
                            self.logger_manager.info(f"複製摘要檔案: {summary_file} -> {summary_path}", "queue_worker")
                        break

                # 如果沒有找到相同內容的摘要，才生成新摘要
                if not skip_summarization:
                    # 準備上傳檔案的資訊作為摘要標頭
                    header_info = {
                        'title': title or audio_file.name,
                        'uploader': '本地上傳',
                        'file_path': str(audio_file),
                        'file_size': audio_file.stat().st_size if audio_file.exists() else 0
                    }

                    self._do_summarize(subtitle_content, summary_path, task_id, header_info)

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

            # 發送摘要郵件（如果摘要存在）
            if summary_path.exists():
                self._send_summary_email(task_id, original_title, summary_path, "音頻")

        except Exception as e:
            error_msg = f"處理音訊檔案時發生錯誤: {str(e)}"
            self.logger_manager.error(error_msg, "queue_worker")
            self.logger_manager.error(f"Error details: {traceback.format_exc()}", "queue_worker")
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
            load_msg = "🔄 載入 Whisper 模型..."
            self._emit_log_to_frontend(task_id, load_msg)
            whisper_manager.load_model()

        transcribe_msg = "🎤 開始語音轉錄..."
        self.logger_manager.info(f"Transcribing audio: {audio_file}", "queue_worker")
        self._emit_log_to_frontend(task_id, transcribe_msg)
        self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=60)

        try:
            success, segments_list = whisper_manager.transcribe_with_fallback(str(audio_file))

            if not success:
                raise RuntimeError("轉錄失敗")

            transcribe_complete_msg = f"✅ 語音轉錄完成，共 {len(segments_list)} 個片段"
            self.logger_manager.info(f"Transcription completed, {len(segments_list)} segments", "queue_worker")
            self._emit_log_to_frontend(task_id, transcribe_complete_msg, 'success')

            srt_content = segments_to_srt(segments_list)

            subtitle_path.parent.mkdir(exist_ok=True)

            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            save_msg = "💾 字幕檔案已儲存"
            self.logger_manager.info(f"Subtitle saved to {subtitle_path}", "queue_worker")
            self._emit_log_to_frontend(task_id, save_msg, 'success')
            self.task_queue.update_task_status(task_id, TaskStatus.PROCESSING, progress=80)

        except Exception as e:
            error_msg = f"❌ 語音轉錄失敗: {str(e)}"
            self.logger_manager.error(f"Transcription error: {e}", "queue_worker")
            self._emit_log_to_frontend(task_id, error_msg, 'error')
            raise

    def _worker_loop(self):
        """工作程式主迴圈"""
        self.logger_manager.info("Worker started", "queue_worker")

        while not self.stop_event.is_set():
            try:
                # 從佇列取得下一個任務
                task = self.task_queue.get_next_task()

                if task is None:
                    # 沒有任務，等待一秒後繼續
                    time.sleep(1)
                    continue

                self.logger_manager.info(f"Processing task {task.task_id} ({task.task_type})", "queue_worker")

                # 根據任務類型處理
                if task.task_type == 'youtube':
                    # 使用 QueueWorker 自己的方法（有字幕擷取功能）
                    self._process_youtube_task(task)
                elif task.task_type == 'upload_media':
                    # 使用 QueueWorker 自己的方法
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
                self.logger_manager.error(f"Unexpected error in worker loop: {e}", "queue_worker")
                self.logger_manager.error(f"Error details: {traceback.format_exc()}", "queue_worker")
                time.sleep(5)  # 發生錯誤時等待一下

        self.logger_manager.info("Worker stopped", "queue_worker")

    def start(self):
        """啟動工作程式"""
        if self.is_running:
            return

        self.is_running = True
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self.logger_manager.info("Worker thread started", "queue_worker")

    def stop(self):
        """停止工作程式"""
        if not self.is_running:
            return

        self.logger_manager.info("Stopping worker...", "queue_worker")
        self.stop_event.set()

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=10)

        self.is_running = False
        self.logger_manager.info("Worker stopped", "queue_worker")

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
