"""
簡體轉繁體工具
使用 OpenCC 進行高品質的簡繁轉換
"""

import logging
from typing import Optional

try:
    import opencc
    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False
    logging.warning("OpenCC 未安裝，簡繁轉換功能將被停用。可使用 pip install opencc-python-reimplemented>=1.1.6 安裝")

class TraditionalConverter:
    """簡體轉繁體轉換器"""

    _instance: Optional['TraditionalConverter'] = None
    _converter = None

    def __new__(cls):
        """實現單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化轉換器"""
        if self._converter is None:
            self._init_converter()

    def _init_converter(self):
        """初始化 OpenCC 轉換器"""
        if OPENCC_AVAILABLE:
            try:
                self._converter = opencc.OpenCC('s2tw.json')
                logging.info("OpenCC 轉換器初始化成功")
            except Exception as e:
                logging.error(f"OpenCC 轉換器初始化失敗: {e}")
                self._converter = None

    def is_available(self) -> bool:
        """檢查轉換器是否可用"""
        return self._converter is not None

    def convert_to_traditional(self, text: str) -> str:
        """
        將文字轉換為繁體中文（台灣正體）

        Args:
            text: 要轉換的文字

        Returns:
            str: 轉換後的繁體中文文字，如果轉換失敗則返回原文
        """
        if not text or not isinstance(text, str):
            return text

        if not self.is_available():
            return text

        try:
            return self._converter.convert(text)
        except Exception as e:
            logging.warning(f"簡繁轉換失敗: {e}")
            return text

# 全域實例
_converter = None

def get_converter() -> TraditionalConverter:
    """獲取轉換器實例"""
    global _converter
    if _converter is None:
        _converter = TraditionalConverter()
    return _converter

# 便捷函數
def to_traditional(text: str) -> str:
    """
    便捷的簡繁轉換函數

    Args:
        text: 要轉換的文字

    Returns:
        str: 轉換後的繁體中文文字
    """
    return get_converter().convert_to_traditional(text)