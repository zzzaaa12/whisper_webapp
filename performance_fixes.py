#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper WebApp 性能優化修復
解決網頁回應慢的問題
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import threading
from typing import Callable, Optional, Any

class PerformanceOptimizer:
    """性能優化管理器"""

    def __init__(self):
        # 創建線程池用於非阻塞操作
        self.thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="perf-")
        self.background_tasks = set()

    def async_task(self, func: Callable) -> Callable:
        """裝飾器：將函數轉為異步執行"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            future = self.thread_pool.submit(func, *args, **kwargs)
            self.background_tasks.add(future)
            # 清理已完成的任務
            self.background_tasks = {f for f in self.background_tasks if not f.done()}
            return future
        return wrapper

    def debounce(self, wait_time: float) -> Callable:
        """防抖裝飾器：延遲執行直到停止調用"""
        def decorator(func: Callable) -> Callable:
            last_called = [0]
            timer = [None]

            @wraps(func)
            def wrapper(*args, **kwargs):
                def delayed_call():
                    last_called[0] = time.time()
                    return func(*args, **kwargs)

                if timer[0]:
                    timer[0].cancel()

                timer[0] = threading.Timer(wait_time, delayed_call)
                timer[0].start()

            return wrapper
        return decorator

    def cache_with_ttl(self, ttl_seconds: int = 300) -> Callable:
        """帶過期時間的緩存裝飾器"""
        def decorator(func: Callable) -> Callable:
            cache = {}

            @wraps(func)
            def wrapper(*args, **kwargs):
                # 創建緩存鍵
                key = str(args) + str(sorted(kwargs.items()))
                current_time = time.time()

                # 檢查緩存
                if key in cache:
                    result, timestamp = cache[key]
                    if current_time - timestamp < ttl_seconds:
                        return result

                # 執行函數並緩存結果
                result = func(*args, **kwargs)
                cache[key] = (result, current_time)

                # 清理過期緩存
                expired_keys = [
                    k for k, (_, ts) in cache.items()
                    if current_time - ts >= ttl_seconds
                ]
                for k in expired_keys:
                    del cache[k]

                return result
            return wrapper
        return decorator

# 全域優化器實例
performance_optimizer = PerformanceOptimizer()

# 優化的 SocketIO 配置
OPTIMIZED_SOCKETIO_CONFIG = {
    'async_mode': 'threading',
    'logger': False,
    'engineio_logger': False,
    'ping_timeout': 60,
    'ping_interval': 25,
    'max_http_buffer_size': 1024 * 1024,  # 1MB
    'allow_upgrades': True,
    'compression': True
}

# 優化的 yt-dlp 配置
OPTIMIZED_YT_DLP_CONFIG = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'socket_timeout': 30,
    'fragment_retries': 3,
    'retries': 2,
    'concurrent_fragment_downloads': 1,  # 避免過度並發
    'buffer_size': 1024 * 16,  # 16KB buffer
}
