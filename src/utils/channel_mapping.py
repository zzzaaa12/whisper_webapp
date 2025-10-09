"""
頻道名稱映射配置
將完整的頻道名稱映射為簡化的顯示名稱
"""

# 頻道名稱映射字典
CHANNEL_DISPLAY_NAMES = {
    "區塊鏈日報 Blockchain Daily": "區塊鏈日報",
    "吳淡如人生實用商學院（Official官方唯一頻道）": "吳淡如人生實用商學院",
    "風傳媒 The Storm Media": "風傳媒",
    "邦妮區塊鏈 Bonnie Blockchain": "邦妮區塊鏈",
}


def get_display_name(channel_name):
    """
    取得頻道的顯示名稱

    Args:
        channel_name: 原始頻道名稱

    Returns:
        顯示名稱（如果有映射則返回映射值，否則返回原始名稱）
    """
    return CHANNEL_DISPLAY_NAMES.get(channel_name, channel_name)


def get_original_name(display_name):
    """
    根據顯示名稱取得原始頻道名稱

    Args:
        display_name: 顯示名稱

    Returns:
        原始頻道名稱（如果找不到則返回顯示名稱本身）
    """
    # 反向查找
    for original, display in CHANNEL_DISPLAY_NAMES.items():
        if display == display_name:
            return original
    return display_name
