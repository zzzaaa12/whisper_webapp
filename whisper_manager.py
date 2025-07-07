"""
統一Whisper模型管理器 - 整合所有模型載入和轉錄邏輯
"""

import torch
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any, Callable
from src.config import get_config
from src.utils.time_formatter import get_timestamp


class WhisperModelManager:
    """統一Whisper模型管理器"""

    def __init__(self, model_name: str = "asadfgglie/faster-whisper-large-v3-zh-TW"):
        self.model_name = model_name
        self.model = None
        self.device = "cpu"
        self.compute_type = "int8"
        self.is_loaded = False

    def load_model(self, prefer_cuda: bool = True, log_callback: Optional[Callable] = None) -> bool:
        """
        統一模型載入函數

        Args:
            prefer_cuda: 是否優先使用CUDA
            log_callback: 日誌回調函數

        Returns:
            bool: 載入是否成功
        """
        try:
            import faster_whisper

            if log_callback:
                log_callback("🔄 載入 Whisper 模型...", 'info')

            # 重置狀態
            self.model = None
            self.is_loaded = False

            # 設定初始設備配置
            self.device = "cpu"
            self.compute_type = "int8"

            # 嘗試使用 CUDA（如果偏好且可用）
            if prefer_cuda and torch.cuda.is_available():
                try:
                    # 測試 CUDA 是否真的可以工作
                    test_tensor = torch.zeros(1, device="cuda")
                    del test_tensor

                    self.device = "cuda"
                    self.compute_type = "float16"

                    if log_callback:
                        log_callback("✅ CUDA 測試成功，使用 GPU 加速", 'success')

                except Exception as cuda_error:
                    if log_callback:
                        log_callback(f"⚠️ CUDA 測試失敗：{cuda_error}，回退到 CPU", 'warning')

                    self.device = "cpu"
                    self.compute_type = "int8"

            # 載入模型
            if log_callback:
                log_callback(f"🔄 載入模型 (設備: {self.device}, 計算類型: {self.compute_type})", 'info')

            self.model = faster_whisper.WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )

            self.is_loaded = True

            if log_callback:
                log_callback(f"✅ Whisper 模型載入成功 ({self.device})", 'success')

            return True

        except Exception as e:
            error_msg = f"❌ Whisper 模型載入失敗: {e}"
            if log_callback:
                log_callback(error_msg, 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')

            self.is_loaded = False
            return False

    def transcribe_with_fallback(
        self,
        audio_file: str,
        log_callback: Optional[Callable] = None,
        **transcribe_kwargs
    ) -> Tuple[bool, Optional[List]]:
        """
        帶回退機制的轉錄函數

        Args:
            audio_file: 音檔路徑
            log_callback: 日誌回調函數
            **transcribe_kwargs: 轉錄參數

        Returns:
            Tuple[bool, Optional[List]]: (成功狀態, 片段列表)
        """
        if not self.is_loaded or not self.model:
            if log_callback:
                log_callback("❌ 模型未載入", 'error')
            return False, None

        # 設定預設轉錄參數
        default_params = {
            'beam_size': 1,
            'language': "zh",
            'vad_filter': True
        }
        default_params.update(transcribe_kwargs)

        try:
            if log_callback:
                log_callback("🎯 開始轉錄音檔...", 'info')
                log_callback("🔄 正在初始化轉錄...", 'info')

            # 第一次嘗試轉錄
            segments, _ = self.model.transcribe(str(audio_file), **default_params)

            if log_callback:
                log_callback("🔄 轉錄進行中，正在處理片段...", 'info')

            # 轉換為列表
            segments_list = list(segments)

            if log_callback:
                log_callback(f"✅ 轉錄完成，共 {len(segments_list)} 個片段", 'success')

            return True, segments_list

        except RuntimeError as e:
            # 檢查是否為CUDA相關錯誤
            if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                if log_callback:
                    log_callback("⚠️ CUDA 錯誤，嘗試使用 CPU 重新轉錄...", 'warning')

                # 嘗試CPU回退
                return self._cpu_fallback_transcribe(audio_file, log_callback, **default_params)
            else:
                if log_callback:
                    log_callback(f"❌ 轉錄失敗: {e}", 'error')
                    log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
                return False, None

        except Exception as e:
            if log_callback:
                log_callback(f"❌ 轉錄失敗: {e}", 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            return False, None

    def _cpu_fallback_transcribe(
        self,
        audio_file: str,
        log_callback: Optional[Callable] = None,
        **transcribe_kwargs
    ) -> Tuple[bool, Optional[List]]:
        """CPU回退轉錄"""
        try:
            import faster_whisper

            if log_callback:
                log_callback("🔄 重新載入 CPU 模型...", 'info')

            # 重新載入CPU模型
            self.model = faster_whisper.WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8"
            )

            self.device = "cpu"
            self.compute_type = "int8"

            # 重新嘗試轉錄
            segments, _ = self.model.transcribe(str(audio_file), **transcribe_kwargs)

            if log_callback:
                log_callback("🔄 CPU 轉錄進行中...", 'info')

            segments_list = list(segments)

            if log_callback:
                log_callback(f"✅ CPU 轉錄完成，共 {len(segments_list)} 個片段", 'success')

            return True, segments_list

        except Exception as cpu_error:
            if log_callback:
                log_callback(f"❌ CPU 轉錄也失敗: {cpu_error}", 'error')
            return False, None

    def get_status(self) -> Dict[str, Any]:
        """獲取模型狀態"""
        return {
            'is_loaded': self.is_loaded,
            'device': self.device,
            'device_name': torch.cuda.get_device_name(0) if self.device == 'cuda' else 'CPU',
            'compute_type': self.compute_type,
            'cuda_available': self.device == 'cuda',
            'model_name': self.model_name,
            'last_updated': get_timestamp()
        }

    def unload_model(self):
        """卸載模型以釋放記憶體"""
        if self.model:
            del self.model
            self.model = None

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.is_loaded = False


# 全域模型管理器實例
whisper_manager = WhisperModelManager()


def get_whisper_manager() -> WhisperModelManager:
    """獲取全域Whisper模型管理器"""
    return whisper_manager


def transcribe_audio(
    audio_file: str,
    log_callback: Optional[Callable] = None,
    auto_load: bool = True,
    **kwargs
) -> Tuple[bool, Optional[List]]:
    """
    便捷音檔轉錄函數

    Args:
        audio_file: 音檔路徑
        log_callback: 日誌回調函數
        auto_load: 是否自動載入模型
        **kwargs: 其他轉錄參數

    Returns:
        Tuple[bool, Optional[List]]: (成功狀態, 片段列表)
    """
    manager = get_whisper_manager()

    # 如果模型未載入且允許自動載入
    if not manager.is_loaded and auto_load:
        if not manager.load_model(log_callback=log_callback):
            return False, None

    return manager.transcribe_with_fallback(audio_file, log_callback, **kwargs)