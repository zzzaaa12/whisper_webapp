"""
統一Whisper模型管理器 - 整合所有模型載入和轉錄邏輯
"""

import os
import platform
import subprocess
import sys
import traceback
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any, Callable

import torch

from src.utils.time_formatter import get_timestamp


@dataclass
class TranscriptSegment:
    """Simple segment container used when third-party libraries return dicts."""
    start: float
    end: float
    text: str


class WhisperModelManager:
    """統一Whisper模型管理器"""

    def __init__(self, model_name: Optional[str] = None, fallback_model_name: Optional[str] = None):
        detected_backend = self._detect_backend()
        self.preferred_backend = detected_backend
        self.backend = detected_backend
        self._backend_reason: Optional[str] = None

        default_model = model_name or os.getenv("WHISPER_MODEL_NAME") or self._get_default_model(detected_backend)
        default_fallback = fallback_model_name or os.getenv("WHISPER_FALLBACK_MODEL_NAME")
        if not default_fallback:
            default_fallback = "asadfgglie/faster-whisper-large-v3-zh-TW"
        if detected_backend != "mlx":
            # 非 MLX 環境下，預設回退模型與主要模型一致
            default_fallback = default_model

        self.primary_model_name = default_model
        self.fallback_model_name = default_fallback
        self.model_name = self.primary_model_name
        self.model = None
        self.device = "cpu"
        self.compute_type = "int8"
        self.is_loaded = False
        self._mlx_module = None
        self._mlx_verified = False
        self._mlx_available = False

        if self.backend == "mlx":
            if not self._verify_mlx_backend():
                self._backend_reason = self._backend_reason or "MLX backend verification failed during startup."


    def _detect_backend(self) -> str:
        """Detect the backend to use based on the current platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        backend_override = os.getenv("WHISPER_BACKEND")
        if backend_override in {"mlx", "faster_whisper"}:
            return backend_override

        if system == "darwin" and machine in {"arm64", "aarch64"}:
            return "mlx"
        return "faster_whisper"

    def _get_default_model(self, backend: Optional[str] = None) -> str:
        """Return the default model name for the detected backend."""
        backend = backend or self.backend
        if backend == "mlx":
            return "mlx-community/whisper-large-v3-turbo-q4"
        return "asadfgglie/faster-whisper-large-v3-zh-TW"

    def _verify_mlx_backend(self) -> bool:
        """Check whether MLX backend can be safely imported and used."""
        if self._mlx_verified:
            return self._mlx_available

        self._mlx_verified = True

        try:
            result = subprocess.run(
                [sys.executable, "-c", "import mlx_whisper"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True
            )
            if result.returncode != 0:
                self._backend_reason = (
                    f"MLX backend check failed with code {result.returncode}: {result.stderr.strip()}"
                )
                self._mlx_available = False
                return False

            self._mlx_available = True
            return True
        except Exception as error:
            self._backend_reason = f"MLX backend check raised exception: {error}"
            self._mlx_available = False
            return False

    def _detect_device_and_compute_type(self, prefer_cuda: bool, log_callback: Optional[Callable]) -> Tuple[str, str]:
        device = "cpu"
        compute_type = "int8"

        if prefer_cuda and torch.cuda.is_available():
            try:
                # 測試 CUDA 是否真的可以工作
                test_tensor = torch.zeros(1, device="cuda")
                del test_tensor

                device = "cuda"
                compute_type = "float16"

                if log_callback:
                    gpu_name = torch.cuda.get_device_name(0)
                    gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    log_callback(f"✅ CUDA 測試成功，使用 GPU 加速", 'success')
                    log_callback(f"📱 GPU 資訊 - 型號: {gpu_name}, 顯存: {gpu_memory:.1f}GB", 'info')

            except Exception as cuda_error:
                if log_callback:
                    log_callback(f"⚠️ CUDA 測試失敗：{cuda_error}，回退到 CPU", 'warning')

                device = "cpu"
                compute_type = "int8"
        return device, compute_type

    def load_model(self, prefer_cuda: bool = True, log_callback: Optional[Callable] = None) -> bool:
        """
        統一模型載入函數

        Args:
            prefer_cuda: 是否優先使用CUDA
            log_callback: 日誌回調函數

        Returns:
            bool: 載入是否成功
        """
        if self.backend == "mlx":
            if not self._verify_mlx_backend():
                if log_callback:
                    reason = self._backend_reason or "MLX backend 無法啟用"
                    log_callback(f"❌ {reason}", 'error')
                else:
                    reason = self._backend_reason or "MLX backend 無法啟用"
                    print(f"[WhisperModelManager] {reason}", flush=True)
                self.is_loaded = False
                return False
            return self._load_mlx_model(log_callback)
        return self._load_faster_whisper_model(prefer_cuda, log_callback)

    def _load_faster_whisper_model(self, prefer_cuda: bool, log_callback: Optional[Callable]) -> bool:
        """Load the model using faster-whisper backend."""
        try:
            import faster_whisper

            if log_callback:
                log_callback(f"🔄 載入 Whisper 模型: {self.model_name}...", 'info')

            # 重置狀態
            self.model = None
            self.is_loaded = False

            # 偵測設備和計算類型
            self.device, self.compute_type = self._detect_device_and_compute_type(prefer_cuda, log_callback)

            # 載入模型
            if log_callback:
                log_callback(f"🔄 載入模型 (模型: {self.model_name}, 設備: {self.device}, 計算類型: {self.compute_type})", 'info')

            self.model = faster_whisper.WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )

            self.is_loaded = True

            if log_callback:
                log_callback(f"✅ Whisper 模型載入成功 (模型: {self.model_name}, 設備: {self.device})", 'success')

            return True

        except Exception as e:
            error_msg = f"❌ Whisper 模型載入失敗: {e}"
            if log_callback:
                log_callback(error_msg, 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')

            self.is_loaded = False
            return False

    def _load_mlx_model(self, log_callback: Optional[Callable]) -> bool:
        """Load the model using MLX backend on Apple Silicon."""
        try:
            import mlx_whisper  # type: ignore

            self._mlx_module = mlx_whisper

            if log_callback:
                log_callback("🔄 載入 MLX Whisper 模型...", 'info')

            # MLX 會在第一次執行時自動下載模型，我們只需確認模組可用
            self.model = None  # MLX 在轉錄時動態載入
            self.device = "mlx"
            self.compute_type = "int4"
            self.is_loaded = True

            if log_callback:
                log_callback("✅ MLX Whisper 模型已就緒 (Apple Silicon)", 'success')

            return True

        except ImportError as e:
            if log_callback:
                log_callback(f"❌ 未找到 MLX Whisper 套件: {e}", 'error')
                log_callback("ℹ️ 請安裝依賴： pip install mlx-whisper", 'info')
            self._backend_reason = f"MLX package import failed: {e}"
            self.is_loaded = False
            return False

        except Exception as e:
            if log_callback:
                log_callback(f"❌ MLX Whisper 模型載入失敗: {e}", 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            self._backend_reason = f"MLX model load failed: {e}"
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
        if not self.is_loaded:
            if log_callback:
                reason_msg = f"❌ 模型未載入" + (f"（原因: {self._backend_reason})" if self._backend_reason else "")
                log_callback(reason_msg, 'error')
            else:
                reason_msg = "Model not loaded"
                if self._backend_reason:
                    reason_msg += f" (reason: {self._backend_reason})"
                print(f"[WhisperModelManager] {reason_msg}", flush=True)
            return False, None

        # 設定預設轉錄參數
        # RTX3060 12GB: batch_size 建議值為 8-16
        # 根據顯存調整 - 更大的batch_size會加快轉錄速度但消耗更多GPU記憶體
        default_params = {
            'beam_size': 1,
            'language': "zh",
            'vad_filter': True
#            'batch_size': 12  # RTX3060 12GB 顯存最佳化
        }
        default_params.update(transcribe_kwargs)

        if self.backend == "mlx":
            success, segments = self._transcribe_mlx(audio_file, log_callback, **default_params)
            return success, segments

        try:
            if log_callback:
                log_callback("🎯 開始轉錄音檔...", 'info')
                log_callback(f"📊 使用模型: {self.model_name}", 'info')
                log_callback(f"⚙️ 轉錄參數 - batch_size: {default_params.get('batch_size', 1)}, beam_size: {default_params.get('beam_size', 1)}, 語言: {default_params.get('language', 'auto')}", 'info')
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
                self._backend_reason = f"RuntimeError: {e}"
                if log_callback:
                    log_callback(f"❌ 轉錄失敗: {e}", 'error')
                    log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
                return False, None

        except Exception as e:
            self._backend_reason = f"{type(e).__name__}: {e}"
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
                log_callback(f"🔄 重新載入 CPU 模型: {self.model_name}...", 'info')

            # 重新載入CPU模型
            self.model = faster_whisper.WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8"
            )

            self.device = "cpu"
            self.compute_type = "int8"

            # 重新嘗試轉錄
            if log_callback:
                log_callback(f"📊 使用模型: {self.model_name} (CPU 模式)", 'info')
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

    def _transcribe_mlx(
        self,
        audio_file: str,
        log_callback: Optional[Callable] = None,
        **transcribe_kwargs
    ) -> Tuple[bool, Optional[List]]:
        """Transcribe audio using the MLX backend."""
        if not self._mlx_module:
            try:
                import mlx_whisper  # type: ignore
                self._mlx_module = mlx_whisper
            except ImportError as import_error:
                if log_callback:
                    log_callback(f"❌ MLX Whisper 套件未安裝: {import_error}", 'error')
                return False, None

        try:
            mlx_whisper = self._mlx_module

            if log_callback:
                log_callback("🎯 使用 MLX 進行轉錄...", 'info')

            decoding_options = None
            language = transcribe_kwargs.get('language')

            if hasattr(mlx_whisper, "DecodingOptions"):
                options_kwargs: Dict[str, Any] = {"task": "transcribe"}
                if language:
                    options_kwargs["language"] = language
                # beam_size 在 MLX 中可選，若存在則附加
                beam_size = transcribe_kwargs.get('beam_size')
                if beam_size is not None:
                    options_kwargs["beam_size"] = beam_size

                try:
                    decoding_options = mlx_whisper.DecodingOptions(**options_kwargs)
                except TypeError:
                    # 若參數不支援，回退到基礎選項
                    decoding_options = mlx_whisper.DecodingOptions(task="transcribe")

            result = None
            file_path = str(audio_file)
            transcribe_kwargs: Dict[str, Any] = {"path_or_hf_repo": self.model_name}
            if decoding_options:
                transcribe_kwargs["options"] = decoding_options
            result = mlx_whisper.transcribe(file_path, **transcribe_kwargs)

            segments_raw = []
            if isinstance(result, dict):
                segments_raw = result.get("segments", [])
            elif hasattr(result, "segments"):
                segments_raw = getattr(result, "segments")
            else:
                segments_raw = result

            segments_list: List[TranscriptSegment] = []
            for segment in segments_raw or []:
                if isinstance(segment, dict):
                    start = float(segment.get("start", 0.0))
                    end = float(segment.get("end", start))
                    text = str(segment.get("text", "")).strip()
                else:
                    start = float(getattr(segment, "start", 0.0))
                    end = float(getattr(segment, "end", start))
                    text = str(getattr(segment, "text", "")).strip()
                segments_list.append(TranscriptSegment(start=start, end=end, text=text))

            if log_callback:
                log_callback(f"✅ MLX 轉錄完成，共 {len(segments_list)} 個片段", 'success')

            return True, segments_list

        except Exception as mlx_error:
            if log_callback:
                log_callback(f"❌ MLX 轉錄失敗: {mlx_error}", 'error')
                log_callback(f"🔍 錯誤詳情: {traceback.format_exc()}", 'error')
            self._backend_reason = f"MLX transcribe failed: {mlx_error}"
            return False, None

    def get_status(self) -> Dict[str, Any]:
        """獲取模型狀態"""
        if self.device == 'cuda':
            device_name = torch.cuda.get_device_name(0)
        elif self.device == 'mlx':
            raw_name = platform.machine()
            device_name = f"Apple Silicon ({raw_name})" if raw_name else "Apple Silicon"
        else:
            device_name = 'CPU'

        return {
            'is_loaded': self.is_loaded,
            'device': self.device,
            'device_name': device_name,
            'compute_type': self.compute_type,
            'cuda_available': self.device == 'cuda',
            'mps_available': self.device == 'mlx',
            'backend': self.backend,
            'preferred_backend': self.preferred_backend,
            'model_name': self.model_name,
            'primary_model_name': self.primary_model_name,
            'fallback_model_name': self.fallback_model_name,
            'backend_reason': self._backend_reason,
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
