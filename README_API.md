# Whisper WebApp API 使用說明

## 概述

Whisper WebApp 現在支援 REST API，可以透過 HTTP 請求發送 YouTube URL 並獲取處理狀態。

## API 端點

### POST /api/process

發送 YouTube URL 到伺服器進行處理。

#### 請求格式

```json
{
    "youtube_url": "https://www.youtube.com/watch?v=example"
}
```

#### 回應格式

**成功 - 伺服器空閒：**
```json
{
    "status": "processing",
    "message": "任務已加入佇列，開始處理",
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "youtube_url": "https://www.youtube.com/watch?v=example"
}
```

**伺服器忙碌：**
```json
{
    "status": "busy",
    "message": "伺服器忙碌中：處理中: https://www.youtube.com/watch?v=OFmvWLBw...",
    "current_task": "處理中: https://www.youtube.com/watch?v=OFmvWLBw..."
}
```

**錯誤：**
```json
{
    "status": "error",
    "message": "錯誤訊息"
}
```

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

### 1. 基本使用

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

### 2. 批次處理

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

### 3. 狀態監控

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

## 注意事項

1. **伺服器狀態**：API 會檢查伺服器狀態，忙碌時會回覆 busy
2. **任務佇列**：空閒時會自動將任務加入佇列並開始處理
3. **錯誤處理**：建議實作重試機制和錯誤處理
4. **網路超時**：預設請求超時為 30 秒
5. **並發限制**：伺服器一次只能處理一個任務

## 執行範例

```bash
# 執行使用範例
python example_usage.py

# 執行命令列 client
python client.py https://www.youtube.com/watch?v=example
``` 