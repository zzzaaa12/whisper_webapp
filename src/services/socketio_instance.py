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
    socketio = SocketIO(
        app,
        async_mode='threading',
        logger=False,
        engineio_logger=False,
        ping_timeout=60,
        ping_interval=25,
        max_http_buffer_size=1024 * 1024,  # 1MB
        allow_upgrades=True,
        compression=True
    )
    return socketio

def get_socketio():
    """取得 SocketIO 實例"""
    return socketio

def emit_log(message, event_type='info', task_id=None):
    """統一的日誌發送函數"""
    if socketio:
        try:
            data = {
                'log': message,  # 移除時間戳，由前端統一添加
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
            socketio.emit('task_log', {
                'task_id': task_id,
                'message': message,  # 移除時間戳，由前端統一添加
                'timestamp': timestamp
            })
        except Exception as e:
            print(f"Error emitting task log: {e}")