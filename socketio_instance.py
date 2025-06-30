"""
SocketIO 實例模組
用於解決循環導入問題，提供全域的 SocketIO 實例
"""

from flask_socketio import SocketIO

# 全域 SocketIO 實例，將在 app.py 中初始化
socketio = None

def init_socketio(app):
    """初始化 SocketIO 實例"""
    global socketio
    socketio = SocketIO(app, async_mode='threading')
    return socketio

def get_socketio():
    """取得 SocketIO 實例"""
    return socketio

def emit_log(message, event_type='info', task_id=None):
    """統一的日誌發送函數"""
    if socketio:
        try:
            from utils import get_timestamp
            timestamp = get_timestamp("time")

            data = {
                'log': f"[{timestamp}] {message}",
                'type': event_type
            }

            if task_id:
                data['task_id'] = task_id

            socketio.emit('update_log', data)
        except Exception as e:
            print(f"Error emitting log: {e}")

def emit_task_log(task_id, message, timestamp=None):
    """發送任務特定的日誌"""
    if socketio:
        try:
            if not timestamp:
                from utils import get_timestamp
                timestamp = get_timestamp("time")

            socketio.emit('task_log', {
                'task_id': task_id,
                'message': f"[{timestamp}] {message}",
                'timestamp': timestamp
            })
        except Exception as e:
            print(f"Error emitting task log: {e}")