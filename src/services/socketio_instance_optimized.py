"""
SocketIO 實例模組 - 性能優化版本
解決循環導入問題，提供全域的 SocketIO 實例
包含性能優化和異步處理
"""

from flask_socketio import SocketIO
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import deque

# 全域 SocketIO 實例，將在 app.py 中初始化
socketio = None

# 優化：批量發送日誌的緩存
log_buffer = deque(maxlen=100)
log_buffer_lock = threading.Lock()
log_send_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="socketio-")

def init_socketio(app):
    """初始化 SocketIO 實例 - 優化版本"""
    global socketio
    socketio = SocketIO(
        app,
        async_mode='threading',
        logger=False,  # 關閉內建日誌以提升性能
        engineio_logger=False,
        ping_timeout=60,
        ping_interval=25,
        max_http_buffer_size=1024 * 1024,  # 1MB
        allow_upgrades=True,
        compression=True,
        cors_allowed_origins="*"  # 允許跨域，減少連接問題
    )

    # 啟動批量日誌發送線程
    _start_batch_log_sender()

    return socketio

def get_socketio():
    """取得 SocketIO 實例"""
    return socketio

def _start_batch_log_sender():
    """啟動批量日誌發送線程"""
    def batch_sender():
        while True:
            time.sleep(0.5)  # 每 500ms 發送一批日誌

            with log_buffer_lock:
                if not log_buffer:
                    continue

                # 取出所有待發送的日誌
                logs_to_send = list(log_buffer)
                log_buffer.clear()

            # 批量發送
            if socketio and logs_to_send:
                for log_data in logs_to_send:
                    try:
                        socketio.emit('update_log', log_data, room=log_data.get('room'))
                    except Exception as e:
                        print(f"Error emitting batched log: {e}")

    # 使用守護線程，避免阻塞主程序退出
    thread = threading.Thread(target=batch_sender, daemon=True)
    thread.start()

def emit_log_optimized(message, event_type='info', task_id=None, room=None):
    """優化版本的日誌發送函數 - 使用批量發送"""
    if not socketio:
        print(f"SocketIO not initialized: {message}")
        return

    log_data = {
        'log': message,
        'type': event_type,
        'room': room
    }

    if task_id:
        log_data['task_id'] = task_id

    # 添加到緩存而不是立即發送
    with log_buffer_lock:
        log_buffer.append(log_data)

def emit_log(message, event_type='info', task_id=None):
    """統一的日誌發送函數 - 向後兼容版本"""
    emit_log_optimized(message, event_type, task_id)

def emit_task_log(task_id, message, timestamp=None):
    """發送任務特定的日誌"""
    if socketio:
        try:
            socketio.emit('task_log', {
                'task_id': task_id,
                'message': message,
                'timestamp': timestamp
            })
        except Exception as e:
            print(f"Error emitting task log: {e}")

def emit_to_room_async(event, data, room=None):
    """異步發送事件到特定房間"""
    def _emit():
        try:
            if socketio:
                socketio.emit(event, data, room=room)
        except Exception as e:
            print(f"Error emitting to room {room}: {e}")

    # 使用線程池異步發送
    log_send_executor.submit(_emit)

def get_connection_count():
    """獲取當前連接數"""
    if socketio:
        try:
            return len(socketio.server.manager.rooms.get('/', {}))
        except:
            return 0
    return 0
