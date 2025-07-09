import json
import uuid
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Callable
import os
from src.config import get_config



class TaskStatus(Enum):
    """任務狀態枚舉"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(Enum):
    """任務類型枚舉"""
    YOUTUBE = "youtube"
    UPLOAD_MEDIA = "upload_media"
    UPLOAD_SUBTITLE = "upload_subtitle"

class Task:
    """任務資料類別"""
    def __init__(self, task_type: str, data: dict, priority: int = 5, user_ip: Optional[str] = None):
        self.task_id = str(uuid.uuid4())
        self.task_type = task_type
        self.status = TaskStatus.QUEUED
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.priority = max(1, min(10, priority))  # 限制在 1-10 之間
        self.user_ip = user_ip or "unknown"
        self.data = data.copy()
        self.result: Dict[str, Any] = {}
        self.error_message = ""
        self.progress = 0

    def to_dict(self) -> dict:
        """轉換為字典格式"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'priority': self.priority,
            'user_ip': self.user_ip,
            'data': self.data,
            'result': self.result,
            'error_message': self.error_message,
            'progress': self.progress
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """從字典創建任務物件"""
        task = cls.__new__(cls)
        task.task_id = data['task_id']
        task.task_type = data['task_type']
        task.status = TaskStatus(data['status'])
        task.created_at = datetime.fromisoformat(data['created_at'])
        task.started_at = datetime.fromisoformat(data['started_at']) if data['started_at'] else None
        task.completed_at = datetime.fromisoformat(data['completed_at']) if data['completed_at'] else None
        task.priority = data['priority']
        task.user_ip = data['user_ip']
        task.data = data['data']
        task.result = data['result']
        task.error_message = data['error_message']
        task.progress = data['progress']
        return task

class TaskQueue:
    """任務佇列管理器"""

    def __init__(self, data_dir: Optional[Path] = None, config_getter: Callable = None):
        self.config_getter = config_getter or get_config
        self.data_dir = data_dir or self.config_getter('PATHS.TASKS_DIR')
        self.tasks_dir = self.data_dir / "tasks"
        self.results_dir = self.data_dir / "results"
        self.queue_file = self.data_dir / "queue_metadata.json"

        # 確保目錄存在
        self.data_dir.mkdir(exist_ok=True)
        self.tasks_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)

        # 任務索引（記憶體中）
        self._tasks: Dict[str, Task] = {}
        self._queue_order: List[str] = []  # 任務ID的排序列表
        self._lock = threading.Lock()

        # 載入現有任務
        self._load_tasks()

    def _load_tasks(self):
        """載入所有任務到記憶體"""
        with self._lock:
            self._tasks.clear()
            self._queue_order.clear()

            # 載入所有任務檔案
            if self.tasks_dir.exists():
                for task_file in self.tasks_dir.glob("*.json"):
                    try:
                        with open(task_file, 'r', encoding='utf-8') as f:
                            task_data = json.load(f)
                        task = Task.from_dict(task_data)
                        self._tasks[task.task_id] = task
                    except Exception as e:
                        print(f"Error loading task {task_file}: {e}")

            # 重建佇列順序（按優先級和建立時間排序）
            queued_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
            self._queue_order = [t.task_id for t in sorted(queued_tasks,
                                                          key=lambda x: (-x.priority, x.created_at))]

            # 清理啟動時處於「處理中」狀態的任務
            processing_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.PROCESSING]
            if processing_tasks:
                print(f"發現 {len(processing_tasks)} 個在啟動時處於處理中狀態的任務，將其標記為失敗。")
                for task in processing_tasks:
                    task.status = TaskStatus.FAILED
                    task.error_message = "任務在應用程式啟動時仍處於處理中狀態，可能因先前的不正常關閉導致。"
                    task.completed_at = datetime.now()
                    self._save_task(task) # 儲存變更

    def _save_task(self, task: Task):
        """儲存單一任務到檔案"""
        task_file = self.tasks_dir / f"{task.task_id}.json"
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)

    def _save_queue_metadata(self):
        """儲存佇列元資料"""
        metadata = {
            'queue_order': self._queue_order,
            'last_updated': datetime.now().isoformat(),
            'total_tasks': len(self._tasks)
        }
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def add_task(self, task_type: str, data: dict, priority: int = 5, user_ip: Optional[str] = None) -> str:
        """新增任務到佇列"""
        task = Task(task_type, data, priority, user_ip)

        with self._lock:
            self._tasks[task.task_id] = task

            # 插入到正確的位置（保持優先級排序）
            inserted = False
            for i, existing_id in enumerate(self._queue_order):
                existing_task = self._tasks[existing_id]
                if (task.priority > existing_task.priority or
                    (task.priority == existing_task.priority and task.created_at < existing_task.created_at)):
                    self._queue_order.insert(i, task.task_id)
                    inserted = True
                    break

            if not inserted:
                self._queue_order.append(task.task_id)

            # 儲存任務
            self._save_task(task)
            self._save_queue_metadata()

        print(f"Added task {task.task_id} ({task_type}) to queue with priority {priority}")
        return task.task_id

    def get_next_task(self) -> Optional[Task]:
        """獲取下一個要處理的任務"""
        with self._lock:
            while self._queue_order:
                task_id = self._queue_order[0]
                task = self._tasks.get(task_id)

                if task and task.status == TaskStatus.QUEUED:
                    # 更新狀態為處理中
                    task.status = TaskStatus.PROCESSING
                    task.started_at = datetime.now()
                    self._queue_order.pop(0)

                    # 儲存更新
                    self._save_task(task)
                    self._save_queue_metadata()

                    return task
                else:
                    # 移除無效的任務ID
                    self._queue_order.pop(0)

            return None

    def update_task_status(self, task_id: str, status: TaskStatus, progress: Optional[int] = None,
                          result: Optional[dict] = None, error_message: Optional[str] = None,
                          log_message: Optional[str] = None, data_update: Optional[dict] = None):
        """更新任務狀態"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            task.status = status
            if progress is not None:
                task.progress = max(0, min(100, progress))
            if result is not None:
                task.result.update(result)
            if error_message is not None:
                task.error_message = error_message
            if data_update is not None:
                task.data.update(data_update)

            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.completed_at = datetime.now()

            # 如果有日誌訊息，嘗試發送到前端
            if log_message:
                self._emit_log_message(task_id, log_message)

            # 儲存更新
            self._save_task(task)

            return True

    def _emit_log_message(self, task_id: str, message: str):
        """發送日誌訊息到前端"""
        try:
            # 嘗試多種方式發送到前端
            from utils import get_timestamp
            timestamp = get_timestamp("time")
            formatted_message = f"[{timestamp}] {message}"

            # 使用統一的 SocketIO 實例發送日誌
            try:
                from socketio_instance import emit_log
                emit_log(message, 'info', task_id)
                print(f"[TASK-{task_id[:8]}] 日誌已發送到前端: {message}")
                return
            except Exception as e:
                print(f"[TASK-{task_id[:8]}] 發送日誌失敗: {e}")

            # 所有方法都失敗，至少在終端輸出
            print(f"[TASK-{task_id[:8]}] {message}")

        except Exception as e:
            # 確保至少在終端輸出
            print(f"[TASK-{task_id[:8]}] {message}")
            print(f"Error emitting log message: {e}")

    def cancel_task(self, task_id: str, access_code: Optional[str] = None) -> tuple[bool, str]:
        """取消任務"""
        # 這裡可以加入通行碼驗證邏輯
        if access_code:
            from utils import validate_access_code
            if not validate_access_code(access_code):
                return False, "通行碼錯誤"

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False, "任務不存在"

            if task.status == TaskStatus.PROCESSING:
                return False, "任務正在處理中，無法取消"

            if task.status != TaskStatus.QUEUED:
                return False, f"任務狀態為 {task.status.value}，無法取消"

            # 更新狀態
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()

            # 從佇列中移除
            if task_id in self._queue_order:
                self._queue_order.remove(task_id)

            # 儲存更新
            self._save_task(task)
            self._save_queue_metadata()

            return True, "任務已取消"

    def get_queue_status(self) -> dict:
        """獲取佇列狀態概覽"""
        with self._lock:
            status_counts = {}
            for status in TaskStatus:
                status_counts[status.value] = 0

            current_task = None
            for task in self._tasks.values():
                status_counts[task.status.value] += 1
                if task.status == TaskStatus.PROCESSING:
                    current_task = task.to_dict()

            return {
                'total_tasks': len(self._tasks),
                'queued': status_counts['queued'],
                'processing': status_counts['processing'],
                'completed': status_counts['completed'],
                'failed': status_counts['failed'],
                'cancelled': status_counts['cancelled'],
                'current_task': current_task,
                'queue_length': len(self._queue_order)
            }

    def get_task_list(self, status: Optional[str] = None, limit: int = 50, user_ip: Optional[str] = None) -> List[dict]:
        """獲取任務列表"""
        with self._lock:
            tasks = list(self._tasks.values())

            # 過濾條件
            if status:
                try:
                    status_enum = TaskStatus(status)
                    tasks = [t for t in tasks if t.status == status_enum]
                except ValueError:
                    pass

            if user_ip:
                tasks = [t for t in tasks if t.user_ip == user_ip]

            # 排序（最新的在前面）
            tasks.sort(key=lambda x: x.created_at, reverse=True)

            # 限制數量
            tasks = tasks[:limit]

            return [task.to_dict() for task in tasks]

    def get_task(self, task_id: str) -> Optional[dict]:
        """獲取單一任務詳情"""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def cleanup_completed_tasks(self, older_than_days: int = 7) -> int:
        """清理已完成的任務"""
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        deleted_count = 0

        with self._lock:
            tasks_to_delete = []

            for task_id, task in self._tasks.items():
                if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                    task.completed_at and task.completed_at < cutoff_date):
                    tasks_to_delete.append(task_id)

            # 刪除任務
            for task_id in tasks_to_delete:
                # 刪除檔案
                task_file = self.tasks_dir / f"{task_id}.json"
                result_file = self.results_dir / f"{task_id}_result.json"

                try:
                    if task_file.exists():
                        task_file.unlink()
                    if result_file.exists():
                        result_file.unlink()

                    # 從記憶體中移除
                    del self._tasks[task_id]
                    if task_id in self._queue_order:
                        self._queue_order.remove(task_id)

                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting task {task_id}: {e}")

            # 儲存更新的元資料
            if deleted_count > 0:
                self._save_queue_metadata()

        return deleted_count

    def get_user_queue_position(self, task_id: str) -> int:
        """獲取任務在佇列中的位置"""
        with self._lock:
            try:
                return self._queue_order.index(task_id) + 1
            except ValueError:
                return -1  # 任務不在佇列中

# 全域任務佇列實例（單例模式）
_task_queue_instance: Optional[TaskQueue] = None
_task_queue_lock = threading.Lock()

def get_task_queue() -> TaskQueue:
    """獲取任務佇列實例（單例模式）"""
    global _task_queue_instance
    if _task_queue_instance is None:
        with _task_queue_lock:
            if _task_queue_instance is None:
                _task_queue_instance = TaskQueue()
    return _task_queue_instance