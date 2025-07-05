"""
媒體處理服務
將 background_worker 的核心處理邏輯拆分成小函數
"""

import traceback
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from utils import sanitize_filename, segments_to_srt, get_timestamp


class MediaProcessor:
    """媒體處理器"""
    
    def __init__(self, folders: Dict[str, Path]):
        self.download_folder = folders.get('download', Path('downloads'))
        self.summary_folder = folders.get('summary', Path('summaries'))
        self.subtitle_folder = folders.get('subtitle', Path('subtitles'))
        self.upload_folder = folders.get('upload', Path('uploads'))
    
    def prepare_file_paths(self, info: Dict[str, Any]) -> tuple[str, Path, Path]:
        """準備檔案路徑"""
        date_str = get_timestamp("date")
        uploader = sanitize_filename(info.get('uploader', '未知頻道'), 30)
        title = sanitize_filename(info.get('title', '未知標題'), 50)
        base_fn = f"{date_str} - {uploader}-{title}"
        
        subtitle_path = self.subtitle_folder / f"{base_fn}.srt"
        summary_path = self.summary_folder / f"{base_fn}.txt"
        
        return base_fn, subtitle_path, summary_path
    
    def check_cache_files(self, subtitle_path: Path, summary_path: Path, 
                         log_callback: Optional[Callable] = None) -> tuple[bool, Optional[str]]:
        """檢查快取檔案是否存在"""
        # 檢查摘要快取
        if summary_path.exists():
            if log_callback:
                log_callback("✅ 找到摘要快取", 'success')
            try:
                summary_content = summary_path.read_text(encoding='utf-8')
                if log_callback:
                    log_callback(f"---\n{summary_content}", 'info')
                return True, summary_content
            except Exception:
                pass
        
        # 檢查字幕快取
        if subtitle_path.exists():
            if log_callback:
                log_callback("✅ 找到字幕快取", 'success')
            try:
                return False, subtitle_path.read_text(encoding='utf-8')
            except Exception:
                pass
        
        return False, None
    
    def download_audio(self, url: str, base_fn: str, 
                      log_callback: Optional[Callable] = None) -> Optional[Path]:
        """下載音檔"""
        try:
            import yt_dlp
            
            if log_callback:
                log_callback("📥 下載音檔中...", 'info')
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(self.download_folder / f"{base_fn}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3'
                }],
                'quiet': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            audio_file = self.download_folder / f"{base_fn}.mp3"
            
            if not audio_file.exists():
                raise FileNotFoundError("下載的音檔不存在")
            
            # 報告檔案大小
            if log_callback:
                file_size = audio_file.stat().st_size / (1024 * 1024)
                log_callback(f"📊 音檔大小: {file_size:.1f} MB", 'info')
            
            return audio_file
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 下載失敗: {e}", 'error')
            return None
    
    def transcribe_audio_file(self, audio_file: Path, model,
                             log_callback: Optional[Callable] = None,
                             cancel_check: Optional[Callable] = None) -> Optional[list]:
        """轉錄音檔"""
        try:
            if log_callback:
                log_callback("🎤 語音辨識中...", 'info')
                log_callback("🔄 載入 Whisper 模型...", 'info')
            
            if not model:
                if log_callback:
                    log_callback("❌ Whisper 模型未載入", 'error')
                return None
            
            # 檢查是否取消
            if cancel_check and cancel_check():
                if log_callback:
                    log_callback("🛑 任務已被取消", 'info')
                return None
            
            if log_callback:
                log_callback("🎯 開始轉錄音檔...", 'info')
                log_callback("🔄 正在初始化轉錄...", 'info')
            
            try:
                # 使用更簡單的參數進行轉錄
                segments, _ = model.transcribe(
                    str(audio_file),
                    beam_size=1,
                    language="zh",
                    vad_filter=True
                )
                
                if log_callback:
                    log_callback("🔄 轉錄進行中，正在處理片段...", 'info')
                
                # 將生成器轉換為列表
                segments_list = list(segments)
                
                if log_callback:
                    log_callback(f"✅ 轉錄完成，共 {len(segments_list)} 個片段", 'success')
                
                return segments_list
                
            except RuntimeError as e:
                return self._handle_transcription_error(e, audio_file, model, log_callback)
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 轉錄失敗: {e}", 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            return None
    
    def _handle_transcription_error(self, error: RuntimeError, audio_file: Path, model,
                                   log_callback: Optional[Callable] = None) -> Optional[list]:
        """處理轉錄錯誤，嘗試 CPU 回退"""
        if "cublas" in str(error).lower() or "cuda" in str(error).lower():
            if log_callback:
                log_callback("⚠️ CUDA 錯誤，嘗試使用 CPU 重新轉錄...", 'warning')
            
            try:
                import faster_whisper
                
                # 重新載入 CPU 模型
                if log_callback:
                    log_callback("🔄 重新載入 CPU 模型...", 'info')
                
                cpu_model = faster_whisper.WhisperModel(
                    "asadfgglie/faster-whisper-large-v3-zh-TW",
                    device="cpu",
                    compute_type="int8"
                )
                
                # 重新嘗試轉錄
                segments, _ = cpu_model.transcribe(
                    str(audio_file),
                    beam_size=1,
                    language="zh",
                    vad_filter=True
                )
                
                if log_callback:
                    log_callback("🔄 CPU 轉錄進行中...", 'info')
                
                segments_list = list(segments)
                
                if log_callback:
                    log_callback(f"✅ CPU 轉錄完成，共 {len(segments_list)} 個片段", 'success')
                
                return segments_list
                
            except Exception as cpu_error:
                if log_callback:
                    log_callback(f"❌ CPU 轉錄也失敗: {cpu_error}", 'error')
                return None
        else:
            if log_callback:
                log_callback(f"❌ 轉錄失敗: {error}", 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            return None
    
    def save_subtitle(self, segments: list, subtitle_path: Path,
                     log_callback: Optional[Callable] = None) -> Optional[str]:
        """儲存字幕檔案"""
        try:
            if log_callback:
                log_callback("📝 生成字幕檔案...", 'info')
            
            srt_content = segments_to_srt(segments)
            subtitle_path.write_text(srt_content, encoding='utf-8')
            
            if log_callback:
                log_callback("📝 字幕已儲存", 'info')
            
            return srt_content
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 字幕儲存失敗: {e}", 'error')
            return None
    
    def generate_summary(self, srt_content: str, summary_path: Path, openai_key: str,
                        header_info: Optional[Dict[str, Any]] = None,
                        log_callback: Optional[Callable] = None,
                        telegram_callback: Optional[Callable] = None) -> bool:
        """生成摘要"""
        try:
            from ai_summary_service import get_summary_service
            from utils import get_config
            
            # 獲取摘要服務
            summary_service = get_summary_service(openai_key, get_config)
            
            # 生成並儲存摘要
            success, result = summary_service.generate_and_save_summary(
                subtitle_content=srt_content,
                save_path=summary_path,
                prompt_type="structured",
                header_info=header_info,
                log_callback=log_callback,
                telegram_callback=telegram_callback
            )
            
            if not success and log_callback:
                log_callback(f"❌ 摘要生成失敗: {result}", 'error')
            
            return success
            
        except ImportError:
            error_msg = "❌ AI摘要服務模組不可用，請檢查 ai_summary_service.py"
            if log_callback:
                log_callback(error_msg, 'error')
            return False
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 摘要生成失敗: {e}", 'error')
            return False
    
    def cleanup_audio_file(self, audio_file: Path, 
                          log_callback: Optional[Callable] = None):
        """清理音檔以節省空間"""
        if audio_file and audio_file.exists():
            try:
                file_size_mb = audio_file.stat().st_size / (1024 * 1024)
                audio_file.unlink()
                
                if log_callback:
                    log_callback(f"🗑️ 已刪除音檔 ({file_size_mb:.1f} MB) 以節省空間", 'info')
                    
            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ 刪除音檔時發生錯誤: {e}", 'warning')
    
    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """取得影片資訊"""
        try:
            import yt_dlp
            
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            # 格式化上傳日期
            upload_date = info.get('upload_date')
            if upload_date:
                upload_date = f"{upload_date[:4]}/{upload_date[4:6]}/{upload_date[6:]}"
            
            return {
                'title': info.get('title', '未知標題'),
                'uploader': info.get('uploader', '未知上傳者'),
                'thumbnail': info.get('thumbnail', ''),
                'duration_string': info.get('duration_string', '未知'),
                'view_count': info.get('view_count', 0),
                'upload_date': upload_date or '未知日期',
                'webpage_url': info.get('webpage_url', url),
                'raw_info': info  # 保留原始資訊
            }
            
        except Exception as e:
            print(f"Error getting video info: {e}")
            return None 