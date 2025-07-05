"""
背景工作程式管理器
重構原來的 background_worker 長函數
"""

import threading
import traceback
from pathlib import Path
from queue import Queue, Empty as QueueEmpty
from typing import Dict, Any, Optional, Callable

from .media_processor import MediaProcessor
from utils import send_telegram_notification


class BackgroundWorkerManager:
    """背景工作程式管理器"""
    
    def __init__(self, folders: Dict[str, Path], openai_key: Optional[str] = None):
        self.folders = folders
        self.openai_key = openai_key
        self.media_processor = MediaProcessor(folders)
        self.model = None
        self.current_task_sid = None
        self.task_lock = threading.Lock()
        
        # 初始化模型
        self._load_model()
    
    def _load_model(self) -> bool:
        """載入 Whisper 模型"""
        try:
            import faster_whisper
            import torch
            
            # 嘗試使用 CUDA，如果失敗則降級到 CPU
            device = "cpu"
            compute = "int8"
            
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
            self.model = faster_whisper.WhisperModel(
                "asadfgglie/faster-whisper-large-v3-zh-TW",
                device=device,
                compute_type=compute
            )
            print("[WORKER] Model loaded successfully.")
            return True
            
        except Exception as e:
            print(f"[WORKER] FATAL: Could not load model: {e}")
            print(f"[WORKER] Error details: {traceback.format_exc()}")
            return False
    
    def create_callbacks(self, sid: str, result_queue: Queue) -> Dict[str, Callable]:
        """建立回調函數"""
        def worker_emit(event: str, data: Dict[str, Any]):
            result_queue.put({'event': event, 'data': data, 'sid': sid})
        
        def worker_update_state(is_busy: bool, task_desc: str):
            result_queue.put({
                'event': 'update_server_state',
                'data': {'is_busy': is_busy, 'current_task': task_desc}
            })
        
        def log_callback(message: str, level: str = 'info'):
            worker_emit('update_log', {'log': message, 'type': level})
        
        def telegram_callback(message: str):
            send_telegram_notification(message)
        
        def cancel_check() -> bool:
            """檢查任務是否被取消"""
            with self.task_lock:
                return self.current_task_sid != sid
        
        return {
            'worker_emit': worker_emit,
            'worker_update_state': worker_update_state,
            'log_callback': log_callback,
            'telegram_callback': telegram_callback,
            'cancel_check': cancel_check
        }
    
    def process_youtube_task(self, task: Dict[str, Any], result_queue: Queue) -> bool:
        """處理 YouTube 任務"""
        sid = task.get('sid')
        url = task.get('audio_url')
        
        if not (sid and url):
            return False
        
        # 設定目前任務
        with self.task_lock:
            self.current_task_sid = sid
        
        try:
            callbacks = self.create_callbacks(sid, result_queue)
            
            callbacks['worker_update_state'](True, f"處理中: {url[:40]}...")
            
            # 取得影片資訊
            info = self.media_processor.get_video_info(url)
            if not info:
                callbacks['log_callback']("❌ 無法獲取影片資訊", 'error')
                return False
            
            # 發送 Telegram 通知
            tg_message = (
                f"*Whisper WebApp 開始處理*\n\n"
                f"▶️ *頻道:* `{info.get('uploader', 'N/A')}`\n"
                f"📄 *標題:* `{info.get('title', 'N/A')}`\n"
                f"🔗 *網址:* {info.get('webpage_url', url)}"
            )
            callbacks['telegram_callback'](tg_message)
            
            # 發送影片資訊到前端
            callbacks['worker_emit']('update_video_info', {
                'title': info['title'],
                'uploader': info['uploader'],
                'thumbnail': info['thumbnail'],
                'duration_string': info['duration_string'],
                'view_count': info['view_count'],
                'upload_date': info['upload_date']
            })
            
            # 準備檔案路徑
            base_fn, subtitle_path, summary_path = self.media_processor.prepare_file_paths(info['raw_info'])
            
            # 檢查快取
            cache_found, cached_content = self.media_processor.check_cache_files(
                subtitle_path, summary_path, callbacks['log_callback']
            )
            
            if cache_found:
                return True  # 找到完整快取，任務完成
            
            srt_content = cached_content
            
            # 如果沒有字幕快取，需要下載和轉錄
            if not srt_content:
                # 檢查取消狀態
                if callbacks['cancel_check']():
                    callbacks['log_callback']("🛑 任務已被取消", 'info')
                    return False
                
                # 下載音檔
                audio_file = self.media_processor.download_audio(
                    url, base_fn, callbacks['log_callback']
                )
                
                if not audio_file:
                    return False
                
                # 檢查取消狀態
                if callbacks['cancel_check']():
                    callbacks['log_callback']("🛑 任務已被取消", 'info')
                    return False
                
                # 轉錄音檔
                segments = self.media_processor.transcribe_audio_file(
                    audio_file, self.model, callbacks['log_callback'], callbacks['cancel_check']
                )
                
                if not segments:
                    return False
                
                # 儲存字幕
                srt_content = self.media_processor.save_subtitle(
                    segments, subtitle_path, callbacks['log_callback']
                )
                
                if not srt_content:
                    return False
                
                # 清理音檔
                self.media_processor.cleanup_audio_file(audio_file, callbacks['log_callback'])
            
            # 生成摘要
            if srt_content and not summary_path.exists():
                if callbacks['cancel_check']():
                    callbacks['log_callback']("🛑 任務已被取消", 'info')
                    return False
                
                header_info = {
                    'title': info['title'],
                    'uploader': info['uploader'],
                    'url': info['webpage_url']
                }
                
                self.media_processor.generate_summary(
                    srt_content, summary_path, self.openai_key,
                    header_info, callbacks['log_callback'], callbacks['telegram_callback']
                )
            
            return True
            
        except Exception as e:
            print(f"Error in process_youtube_task: {e}")
            print(f"Error details: {traceback.format_exc()}")
            return False
        finally:
            # 清除目前任務
            with self.task_lock:
                if self.current_task_sid == sid:
                    self.current_task_sid = None
    
    def process_audio_file_task(self, task: Dict[str, Any], result_queue: Queue) -> bool:
        """處理音檔任務"""
        sid = task.get('sid')
        audio_file = task.get('audio_file')
        subtitle_path = task.get('subtitle_path')
        summary_path = task.get('summary_path')
        
        if not all([sid, audio_file, subtitle_path, summary_path]):
            return False
        
        # 設定目前任務
        with self.task_lock:
            self.current_task_sid = sid or "broadcast_task"
        
        try:
            callbacks = self.create_callbacks(sid, result_queue)
            
            callbacks['log_callback']("🔄 工作程序已接收音訊檔案任務...", 'info')
            callbacks['worker_update_state'](True, f"處理音訊檔案: {Path(audio_file).name[:40]}...")
            
            # 檢查音檔是否存在
            audio_path = Path(audio_file)
            if not audio_path.exists():
                callbacks['log_callback'](f"❌ 音檔不存在: {audio_file}", 'error')
                return False
            
            # 報告檔案大小
            file_size = audio_path.stat().st_size
            callbacks['log_callback'](f"📊 音檔大小: {file_size / (1024*1024):.1f} MB", 'info')
            
            # 轉錄音檔
            segments = self.media_processor.transcribe_audio_file(
                audio_path, self.model, callbacks['log_callback']
            )
            
            if not segments:
                return False
            
            # 儲存字幕
            srt_content = self.media_processor.save_subtitle(
                segments, Path(subtitle_path), callbacks['log_callback']
            )
            
            if not srt_content:
                return False
            
            # 生成摘要
            if self.openai_key:
                header_info = {'filename': audio_path.name}
                
                self.media_processor.generate_summary(
                    srt_content, Path(summary_path), self.openai_key,
                    header_info, callbacks['log_callback'], callbacks['telegram_callback']
                )
            
            # 刪除音檔以節省空間
            self.media_processor.cleanup_audio_file(audio_path, callbacks['log_callback'])
            
            return True
            
        except Exception as e:
            print(f"Error in process_audio_file_task: {e}")
            print(f"Error details: {traceback.format_exc()}")
            return False
        finally:
            # 清除目前任務
            with self.task_lock:
                if self.current_task_sid == (sid or "broadcast_task"):
                    self.current_task_sid = None
    
    def cancel_current_task(self, sid: str) -> bool:
        """取消目前任務"""
        with self.task_lock:
            if self.current_task_sid == sid:
                self.current_task_sid = None
                return True
            return False 