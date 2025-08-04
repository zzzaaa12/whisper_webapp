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

from src.core.task_queue import get_task_queue, TaskStatus
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

        # 工作線程
        self.worker_thread = None
        self.is_running = False
        self.yt_dlp = yt_dlp # Assign yt_dlp here

    # _get_config 已移除，統一使用 utils.get_config

    # _send_telegram_notification 已移除，統一使用 utils.send_telegram_notification



    # _sanitize_filename 已移除，統一使用 utils.sanitize_filename


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
                    result = self.task_processor.process_youtube_task(task)
                    # 確保任務狀態正確更新為完成
                    self.task_queue.update_task_status(
                        task.task_id, TaskStatus.COMPLETED, progress=100, result=result
                    )
                elif task.task_type == 'upload_media':
                    result = self.task_processor.process_upload_media_task(task)
                    # 確保任務狀態正確更新為完成
                    self.task_queue.update_task_status(
                        task.task_id, TaskStatus.COMPLETED, progress=100, result=result
                    )
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
