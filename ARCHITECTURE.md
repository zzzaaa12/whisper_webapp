# Whisper WebApp 架構文檔

## 專案結構

```
whisper_webapp/
├── app.py                          # 主程式入口點
├── config.example.json             # 配置範例檔案
├── requirements.txt                 # Python 依賴
├── README.md                       # 專案說明
├──
├── src/                            # 核心應用程式碼
│   ├── core/                       # 核心業務邏輯
│   │   ├── __init__.py
│   │   └── task_queue.py           # 任務佇列管理
│   │
│   ├── services/                   # 業務服務層
│   │   ├── auth_service.py         # 認證服務
│   │   ├── file_service.py         # 檔案操作服務
│   │   ├── queue_worker.py         # 佇列工作程式
│   │   ├── task_processor.py       # 任務處理器
│   │   ├── whisper_manager.py      # Whisper 模型管理
│   │   ├── ai_summary_service.py   # AI 摘要服務
│   │   └── ...
│   │
│   ├── routes/                     # 路由層
│   │   ├── main.py                 # 主要頁面路由
│   │   └── api.py                  # API 路由
│   │
│   ├── middleware/                 # 中介軟體層
│   │   ├── __init__.py
│   │   └── error_handler.py        # 統一錯誤處理
│   │
│   ├── utils/                      # 工具函數
│   │   ├── file_sanitizer.py       # 檔案名清理
│   │   ├── filename_matcher.py     # 檔名比對
│   │   ├── logger_manager.py       # 日誌管理
│   │   ├── api_response.py         # API 回應格式
│   │   ├── config_validator.py     # 配置驗證
│   │   └── ...
│   │
│   ├── app_factory.py              # Flask 應用程式工廠
│   ├── socketio_handlers.py        # SocketIO 事件處理
│   └── config.py                   # 配置管理
│
├── examples/                       # 使用範例
│   └── python_client.py            # Python 客戶端範例
│
├── scripts/                        # 工具腳本
│   └── clean_trailing_whitespace.py
│
├── templates/                      # HTML 模板
├── static/                         # 靜態資源
├── logs/                          # 日誌檔案
├── summaries/                     # 生成的摘要
├── subtitles/                     # 生成的字幕
└── trash/                         # 回收桶
```

## 架構層次

### 1. 入口層 (Entry Layer)
- `app.py` - 應用程式啟動點，負責初始化和啟動

### 2. 應用層 (Application Layer)
- `src/app_factory.py` - Flask 應用程式工廠
- `src/socketio_handlers.py` - WebSocket 事件處理

### 3. 路由層 (Route Layer)
- `src/routes/main.py` - 網頁路由
- `src/routes/api.py` - API 路由

### 4. 服務層 (Service Layer)
- 業務邏輯的核心實現
- 各種服務的封裝和管理

### 5. 核心層 (Core Layer)
- `src/core/task_queue.py` - 任務佇列核心邏輯

### 6. 工具層 (Utility Layer)
- 通用工具函數和輔助類

## 設計原則

### 1. 單一職責原則 (SRP)
每個模組都有明確的單一職責：
- `auth_service.py` 只負責認證
- `file_service.py` 只負責檔案操作
- `task_processor.py` 只負責任務處理

### 2. 依賴注入 (DI)
- 服務通過參數傳遞，而非全域變數
- 提高可測試性和模組化程度

### 3. 分層架構
- 清晰的分層結構
- 上層依賴下層，下層不依賴上層

### 4. 配置集中化
- 所有配置統一在 `src/config.py` 管理
- 支援環境變數和 JSON 配置檔案

## 資料流

```
用戶請求 → 路由層 → 服務層 → 核心層 → 資料庫/檔案系統
         ↓
    SocketIO 事件 → 事件處理器 → 服務層 → 任務佇列
```

## 重構歷程

### 階段一：清理未使用程式碼 ✅
- 合併 `DirectoryManager` 到 `FileService`
- 合併 `FileValidator` 到 `main.py`
- 移動工具檔案到 `scripts/`
- 移動客戶端到 `examples/`

### 階段二：拆分 app.py ✅
- 創建應用程式工廠模式
- 分離 SocketIO 事件處理
- 簡化主程式邏輯

### 階段三：重組核心模組 ✅
- 移動 `task_queue.py` 到 `src/core/`
- 統一導入路徑
- 建立清晰的架構層次

### 階段四：統一 API 回應和錯誤處理 ✅
- 統一所有 API 端點使用 `APIResponse` 類
- 創建全域錯誤處理中介軟體
- 添加配置驗證工具
- 改善錯誤日誌記錄

## 未來改進方向

1. **測試覆蓋** - 為每個服務添加單元測試
2. **API 文檔** - 使用 OpenAPI/Swagger 生成 API 文檔
3. **監控系統** - 添加健康檢查和監控端點
4. **容器化** - 添加 Docker 支援
5. **CI/CD** - 建立自動化測試和部署流程