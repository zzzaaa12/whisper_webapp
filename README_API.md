# Whisper WebApp API 使用說明

## 概述

Whisper WebApp 提供完整的 REST API，支援 YouTube 影片處理、檔案上傳、摘要管理、書籤管理、回收桶操作等功能。

## API 端點總覽

### 影片處理 API
- `POST /api/process` - 處理 YouTube 影片
- `POST /api/verify_access_code` - 驗證通行碼

### 檔案上傳 API
- `POST /api/upload_subtitle` - 上傳字幕檔案
- `POST /api/upload_media` - 上傳媒體檔案

### 書籤管理 API
- `POST /api/bookmarks/add` - 新增書籤
- `POST /api/bookmarks/remove` - 移除書籤
- `GET /api/bookmarks/list` - 獲取書籤列表
- `GET /api/bookmarks/check/<filename>` - 檢查是否已加入書籤

### 回收桶管理 API
- `POST /api/trash/move` - 移動檔案到回收桶
- `POST /api/trash/restore` - 從回收桶還原檔案
- `POST /api/trash/delete` - 永久刪除回收桶檔案
- `GET /api/trash/list` - 獲取回收桶列表

### 系統狀態 API
- `GET /api/system/config-status` - 獲取系統配置狀態

---

## 詳細 API 說明

### 1. 影片處理 API

#### POST /api/process

處理 YouTube 影片，進行語音轉文字和摘要生成。

**請求格式：**
```json
{
    "youtube_url": "https://www.youtube.com/watch?v=example",
    "access_code": "your_access_code"
}
```

**回應格式：**

成功 - 伺服器空閒：
```json
{
    "status": "processing",
    "message": "任務已加入佇列，開始處理",
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "youtube_url": "https://www.youtube.com/watch?v=example"
}
```

伺服器忙碌：
```json
{
    "status": "busy",
    "message": "伺服器忙碌中：處理中: https://www.youtube.com/watch?v=...",
    "current_task": "處理描述"
}
```

#### POST /api/verify_access_code

驗證通行碼是否正確。

**請求格式：**
```json
{
    "access_code": "your_access_code"
}
```

**回應格式：**
```json
{
    "success": true,
    "message": "通行碼正確"
}
```

### 2. 檔案上傳 API

#### POST /api/upload_subtitle

上傳字幕檔案到摘要目錄。

**請求格式：** (multipart/form-data)
- `file`: 字幕檔案
- `access_code`: 通行碼
- `filename`: 檔案名稱（可選）

**回應格式：**
```json
{
    "success": true,
    "message": "檔案上傳成功",
    "filename": "processed_filename.txt",
    "title": "檔案標題",
    "file_size": 1024,
    "task_id": "unique_task_id"
}
```

#### POST /api/upload_media

上傳媒體檔案進行處理。

**請求格式：** (multipart/form-data)
- `file`: 媒體檔案
- `access_code`: 通行碼

**回應格式：**
```json
{
    "success": true,
    "message": "檔案上傳成功，開始處理",
    "filename": "processed_filename.mp3",
    "task_id": "unique_task_id"
}
```

### 3. 書籤管理 API

#### POST /api/bookmarks/add

新增書籤。

**請求格式：**
```json
{
    "filename": "summary_file.txt",
    "title": "摘要標題（可選）"
}
```

#### POST /api/bookmarks/remove

移除書籤。

**請求格式：**
```json
{
    "filename": "summary_file.txt"
}
```

#### GET /api/bookmarks/list

獲取書籤列表。

**回應格式：**
```json
{
    "success": true,
    "bookmarks": [
        {
            "filename": "file1.txt",
            "title": "摘要1",
            "created_at": "2024-01-01T00:00:00",
            "file_size": 1024,
            "preview": "摘要預覽..."
        }
    ]
}
```

#### GET /api/bookmarks/check/<filename>

檢查檔案是否已加入書籤。

**回應格式：**
```json
{
    "success": true,
    "is_bookmarked": true
}
```

### 4. 回收桶管理 API

#### POST /api/trash/move

移動檔案到回收桶。

**請求格式：**
```json
{
    "files": [
        {
            "path": "file1.txt",
            "type": "summary"
        },
        {
            "path": "file2.srt",
            "type": "subtitle"
        }
    ]
}
```

#### POST /api/trash/restore

從回收桶還原檔案。

**請求格式：**
```json
{
    "trash_id": "unique_trash_id"
}
```

#### POST /api/trash/delete

永久刪除回收桶檔案。

**請求格式：**
```json
{
    "trash_id": "unique_trash_id"
}
```

#### GET /api/trash/list

獲取回收桶列表。

**回應格式：**
```json
{
    "success": true,
    "items": [
        {
            "id": "unique_id",
            "original_path": "file.txt",
            "file_type": "summary",
            "deleted_at": "2024-01-01T00:00:00",
            "file_size": 1024
        }
    ]
}
```

### 5. 系統狀態 API

#### GET /api/system/config-status

獲取系統配置狀態。

**回應格式：**
```json
{
    "success": true,
    "config_status": {
        "access_code_set": true,
        "openai_api_key_set": true,
        "telegram_configured": false
    }
}
```

---

## Python Client 使用

### 安裝依賴

```bash
pip install requests
```

### 基本使用

```python
from client import WhisperClient

# 建立客戶端
client = WhisperClient("http://localhost:5000")

# 檢查伺服器狀態
status = client.check_server_status()
print(status)

# 發送 YouTube URL
result = client.send_youtube_url("https://www.youtube.com/watch?v=example")
print(result)
```

### 命令列使用

```bash
# 基本使用
python client.py https://www.youtube.com/watch?v=example

# 指定伺服器網址
python client.py https://www.youtube.com/watch?v=example --server http://192.168.1.100:5000
```

### 回應格式

Client 方法會回傳以下格式的字典：

```python
{
    'success': True/False,           # 是否成功
    'status': 'processing/busy/error',  # 狀態
    'message': '狀態描述',           # 訊息
    'task_id': '任務ID',            # 任務ID（如果正在處理）
    'http_code': 200                # HTTP 狀態碼
}
```

## 使用範例

### 1. 基本影片處理

```python
from client import WhisperClient

client = WhisperClient()
result = client.send_youtube_url("https://www.youtube.com/watch?v=example")

if result['success']:
    if result['status'] == 'processing':
        print("✅ 任務已開始處理")
    elif result['status'] == 'busy':
        print("⚠️  伺服器忙碌中")
else:
    print(f"❌ 錯誤：{result['message']}")
```

### 2. 檔案上傳範例

```python
import requests

# 上傳字幕檔案
with open('subtitle.txt', 'rb') as f:
    files = {'file': f}
    data = {'access_code': 'your_code', 'filename': 'my_subtitle.txt'}
    response = requests.post('http://localhost:5000/api/upload_subtitle',
                           files=files, data=data)
    print(response.json())
```

### 3. 書籤管理範例

```python
import requests

# 新增書籤
data = {
    'filename': 'summary.txt',
    'title': '重要摘要'
}
response = requests.post('http://localhost:5000/api/bookmarks/add', json=data)
print(response.json())

# 獲取書籤列表
response = requests.get('http://localhost:5000/api/bookmarks/list')
bookmarks = response.json()['bookmarks']
```

### 4. 批次處理

```python
from client import WhisperClient
import time

client = WhisperClient()
urls = [
    "https://www.youtube.com/watch?v=video1",
    "https://www.youtube.com/watch?v=video2",
    "https://www.youtube.com/watch?v=video3"
]

for url in urls:
    result = client.send_youtube_url(url)
    if result['status'] == 'busy':
        print("伺服器忙碌，等待...")
        time.sleep(10)  # 等待 10 秒
    elif result['status'] == 'processing':
        print("任務已加入佇列")
        time.sleep(2)   # 等待 2 秒再處理下一個
```

### 5. 狀態監控

```python
from client import WhisperClient
import time

client = WhisperClient()

# 持續監控伺服器狀態
while True:
    status = client.check_server_status()
    if status['success']:
        print("✅ 伺服器正常運行")
    else:
        print("❌ 伺服器離線")

    time.sleep(30)  # 每 30 秒檢查一次
```

## 錯誤處理

### 常見錯誤

1. **連接錯誤**：伺服器未運行或網路問題
2. **格式錯誤**：請求格式不正確
3. **URL 錯誤**：無效的 YouTube URL
4. **伺服器忙碌**：伺服器正在處理其他任務
5. **通行碼錯誤**：通行碼不正確或未提供
6. **檔案錯誤**：檔案格式不支援或檔案過大

### 錯誤處理範例

```python
from client import WhisperClient

client = WhisperClient()

try:
    result = client.send_youtube_url("https://www.youtube.com/watch?v=example")

    if not result['success']:
        if result['http_code'] == 0:
            print("網路連接問題")
        elif result['status'] == 'busy':
            print("伺服器忙碌，稍後重試")
        else:
            print(f"其他錯誤：{result['message']}")
    else:
        print("請求成功")

except Exception as e:
    print(f"發生異常：{e}")
```

## 安全性考量

1. **通行碼保護**：所有敏感操作都需要通行碼驗證
2. **檔案大小限制**：上傳檔案有大小限制（預設 500MB）
3. **檔案類型檢查**：只接受特定類型的檔案
4. **路徑安全**：防止路徑遍歷攻擊
5. **IP 限制**：支援 IP 封鎖和登入嘗試限制

## 注意事項

1. **伺服器狀態**：API 會檢查伺服器狀態，忙碌時會回覆 busy
2. **任務佇列**：空閒時會自動將任務加入佇列並開始處理
3. **錯誤處理**：建議實作重試機制和錯誤處理
4. **網路超時**：預設請求超時為 30 秒
5. **並發限制**：伺服器一次只能處理一個任務
6. **檔案編碼**：上傳的文字檔案請使用 UTF-8 編碼