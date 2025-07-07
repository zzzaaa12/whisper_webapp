
from datetime import datetime

class TimeFormatter:
    """統一時間格式化器"""

    @staticmethod
    def get_timestamp(format_type: str = "default") -> str:
        """統一時間格式化函數"""
        now = datetime.now()

        formats = {
            "default": "%Y-%m-%d %H:%M:%S",
            "log": "%m/%d %H:%M:%S",
            "file": "%Y%m%d_%H%M%S",
            "date": "%Y.%m.%d",
            "display": "%Y-%m-%d %H:%M:%S"
        }

        return now.strftime(formats.get(format_type, formats["default"]))

# 便捷函數導出
def get_timestamp(format_type: str = "default") -> str:
    """便捷時間格式化函數"""
    return TimeFormatter.get_timestamp(format_type)
