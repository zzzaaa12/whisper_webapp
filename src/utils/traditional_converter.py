"""
Simplified-to-Traditional Chinese conversion helper.

OpenCC is optional. If it is not installed, callers get the original text back.
"""

import logging
from typing import Optional

try:
    import opencc

    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False
    logging.warning(
        "OpenCC unavailable; install with "
        "pip install opencc-python-reimplemented>=0.1.7"
    )


class TraditionalConverter:
    """Lazy singleton wrapper around OpenCC."""

    _instance: Optional["TraditionalConverter"] = None
    _converter = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._converter is None:
            self._init_converter()

    def _init_converter(self):
        if OPENCC_AVAILABLE:
            try:
                self._converter = opencc.OpenCC("s2tw.json")
                logging.info("OpenCC converter initialized")
            except Exception as e:
                logging.error(f"OpenCC converter initialization failed: {e}")
                self._converter = None

    def is_available(self) -> bool:
        return self._converter is not None

    def convert_to_traditional(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        if not self.is_available():
            return text

        try:
            return self._converter.convert(text)
        except Exception as e:
            logging.warning(f"Traditional Chinese conversion failed: {e}")
            return text


_converter = None


def get_converter() -> TraditionalConverter:
    global _converter
    if _converter is None:
        _converter = TraditionalConverter()
    return _converter


def to_traditional(text: str) -> str:
    return get_converter().convert_to_traditional(text)
