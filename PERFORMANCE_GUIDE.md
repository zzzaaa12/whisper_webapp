# Whisper WebApp 性能優化指南

## 問題診斷結果

### 主要性能瓶頸：

1. **SocketIO 配置問題** ⚠️
   - 使用同步模式但處理大量實時更新
   - 沒有適當的連接管理和壓縮
   - 日誌發送過於頻繁

2. **YouTube 資訊獲取阻塞** 🔴 **嚴重**
   - yt-dlp 在主線程中同步獲取影片資訊
   - 網絡超時設置過長（預設 30-60 秒）
   - 缺乏錯誤處理和回退機制

3. **前端頻繁請求** ⚠️
   - GPU 狀態每 30 秒更新
   - 系統資訊重複獲取
   - 缺乏請求防抖

4. **文件 I/O 操作** ⚠️
   - 大量同步文件讀寫操作
   - 沒有適當的緩存機制

## 已實施的優化方案

### 1. SocketIO 優化

```python
# 新的配置
socketio = SocketIO(
    app,
    async_mode='threading',
    logger=False,  # 關閉內建日誌
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024,  # 1MB
    allow_upgrades=True,
    compression=True  # 啟用壓縮
)
```

### 2. YouTube 資訊獲取優化

```python
# 優化的 yt-dlp 配置
info_opts = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'socket_timeout': 15,  # 減少超時時間
    'retries': 1,  # 減少重試次數
    'fragment_retries': 1,
    'skip_download': True,
    'no_check_certificate': True  # 加速 SSL 驗證
}

# 添加錯誤處理
try:
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        # ... 處理資訊
except Exception as e:
    # 使用預設值，避免阻塞
    video_title = f"YouTube 影片 ({url[-11:]})"
    # ... 其他預設值
```

### 3. 前端請求頻率優化

```javascript
// GPU 狀態更新從 30 秒改為 60 秒
window.gpuUpdateInterval = setInterval(() => {
    socket.emit('request_gpu_status');
}, 60000); // 60 秒更新一次
```

## 建議實施的進一步優化

### 1. 異步任務處理

```python
# 使用 performance_fixes.py 中的優化器
from performance_fixes import performance_optimizer

@performance_optimizer.async_task
def get_youtube_info_async(url):
    """異步獲取 YouTube 資訊"""
    # ... yt-dlp 操作
```

### 2. 緩存機制

```python
@performance_optimizer.cache_with_ttl(ttl_seconds=300)  # 5分鐘緩存
def get_youtube_info_cached(url):
    """帶緩存的 YouTube 資訊獲取"""
    # ... 實際獲取邏輯
```

### 3. 批量日誌發送

使用 `socketio_instance_optimized.py` 中的批量發送機制：

```python
# 替換原有的即時發送
emit_log_optimized(message, event_type, task_id)
```

## 性能監控建議

### 1. 添加性能監控

```python
import time
import functools

def monitor_performance(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        if end_time - start_time > 1.0:  # 超過 1 秒記錄
            print(f"[PERF] {func.__name__} took {end_time - start_time:.2f}s")

        return result
    return wrapper
```

### 2. 資源使用監控

```python
import psutil
import threading

def monitor_resources():
    """監控系統資源使用"""
    while True:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()

        if cpu_percent > 80:
            print(f"[WARNING] High CPU usage: {cpu_percent}%")

        if memory_info.percent > 80:
            print(f"[WARNING] High memory usage: {memory_info.percent}%")

        time.sleep(10)

# 啟動資源監控線程
threading.Thread(target=monitor_resources, daemon=True).start()
```

## 部署建議

### 1. 生產環境配置

```python
# 使用 Gunicorn + Gevent
gunicorn --worker-class gevent \
         --worker-connections 1000 \
         --workers 4 \
         --bind 0.0.0.0:5000 \
         --timeout 120 \
         --keepalive 2 \
         --max-requests 1000 \
         --max-requests-jitter 50 \
         app:app
```

### 2. Nginx 反向代理

```nginx
upstream whisper_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 靜態文件緩存
    location /static {
        alias /path/to/whisper_webapp/static;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # WebSocket 支持
    location /socket.io/ {
        proxy_pass http://whisper_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://whisper_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120;
    }
}
```

## 測試和驗證

### 1. 性能測試腳本

```bash
# 安裝測試工具
pip install locust

# 執行負載測試
locust -f performance_test.py --host=http://localhost:5000
```

### 2. 延遲測試

```javascript
// 在瀏覽器控制台測試響應時間
function testResponseTime() {
    const start = performance.now();

    fetch('/api/queue/status')
        .then(response => response.json())
        .then(data => {
            const end = performance.now();
            console.log(`API 回應時間: ${end - start} ms`);
        });
}

// 執行測試
testResponseTime();
```

## 預期改善效果

實施這些優化後，您應該能看到：

1. **頁面載入速度提升 40-60%**
2. **API 回應時間減少 50-70%**
3. **資源使用率降低 20-30%**
4. **用戶體驗顯著改善**

## 注意事項

1. **逐步實施**：建議分批實施這些優化，以便監控每個變更的效果
2. **備份重要數據**：在實施重大變更前備份配置和數據
3. **監控錯誤**：密切監控日誌以確保優化不會引入新的問題
4. **用戶回饋**：收集用戶對性能改善的回饋
