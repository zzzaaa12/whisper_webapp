import os
import torch
from typing import Dict, Any, Tuple

from src.utils.time_formatter import get_timestamp

class GPUService:
    """GPU 狀態服務"""

    def __init__(self):
        self.gpu_status = {
            'device': 'unknown',
            'device_index': None,
            'device_name': 'unknown',
            'cuda_available': False,
            'mps_available': False,
            'last_updated': None
        }

    def _get_cuda_device_index(self) -> int:
        raw_value = os.getenv("WHISPER_CUDA_DEVICE_INDEX")
        if raw_value is None:
            try:
                from src.config import get_config
                raw_value = get_config("whisper.cuda_device_index", 0)
            except Exception:
                raw_value = 0

        try:
            device_index = int(raw_value)
        except (TypeError, ValueError):
            device_index = 0

        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            if device_count > 0 and not 0 <= device_index < device_count:
                device_index = 0

        return device_index

    def _detect_cuda_device_info(self) -> Tuple[str, int, str, bool, bool]:
        device = "cpu"
        device_index = None
        device_name = "CPU"
        cuda_available = torch.cuda.is_available()
        mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

        if cuda_available:
            try:
                device_index = self._get_cuda_device_index()
                torch.cuda.set_device(device_index)
                test_tensor = torch.zeros(1, device=f"cuda:{device_index}")
                del test_tensor
                device = "cuda"
                device_name = torch.cuda.get_device_name(device_index)
            except Exception as e:
                print(f"CUDA 測試失敗: {e}")
                device = "cpu"
                device_name = "CPU (CUDA 不可用)"
                cuda_available = False
        elif mps_available:
            device = "mps"
            device_name = "Apple Silicon (MPS)"

        return device, device_index, device_name, cuda_available, mps_available

    def get_gpu_status(self) -> Dict[str, Any]:
        """獲取 GPU 狀態資訊"""
        try:
            device, device_index, device_name, cuda_available, mps_available = self._detect_cuda_device_info()

            self.gpu_status.update({
                'device': device,
                'device_index': device_index,
                'device_name': device_name,
                'cuda_available': cuda_available,
                'mps_available': mps_available,
                'last_updated': get_timestamp("default")
            })

            return self.gpu_status.copy()

        except Exception as e:
            print(f"獲取 GPU 狀態時發生錯誤: {e}")
            return self.gpu_status.copy()
