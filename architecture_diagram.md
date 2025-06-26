# Whisper WebApp 功能架構圖

## 系統架構概覽

```mermaid
graph TB
    subgraph "外部介面層"
        A[Web 瀏覽器] 
        B[Python Client]
        C[Telegram Bot]
    end
    
    subgraph "API 層"
        D[Flask Web Server]
        E[Socket.IO Server]
        F[REST API /api/process]
    end
    
    subgraph "業務邏輯層"
        G[任務佇列管理]
        H[狀態管理]
        I[登入驗證]
        J[IP 封鎖管理]
    end
    
    subgraph "背景處理層"
        K[背景工作程序]
        L[YouTube 下載器]
        M[Whisper 轉錄引擎]
        N[OpenAI 摘要引擎]
    end
    
    subgraph "資料儲存層"
        O[音檔儲存]
        P[字幕檔案]
        Q[摘要檔案]
        R[日誌檔案]
    end
    
    subgraph "外部服務"
        S[YouTube]
        T[OpenAI API]
        U[Telegram API]
    end
    
    A --> D
    A --> E
    B --> F
    C --> U
    D --> G
    D --> H
    D --> I
    D --> J
    E --> G
    E --> H
    F --> G
    F --> H
    G --> K
    K --> L
    K --> M
    K --> N
    L --> S
    L --> O
    M --> P
    N --> T
    N --> Q
    K --> R
```

## 詳細功能架構

```mermaid
graph LR
    subgraph "前端介面"
        A1[主頁面 - 表單輸入]
        A2[摘要列表頁面]
        A3[摘要詳情頁面]
        A4[管理頁面]
        A5[即時日誌顯示]
        A6[取消按鈕]
    end
    
    subgraph "後端 API"
        B1[Flask 路由]
        B2[Socket.IO 事件]
        B3[REST API 端點]
        B4[靜態檔案服務]
    end
    
    subgraph "核心功能"
        C1[YouTube URL 處理]
        C2[音檔下載]
        C3[語音轉錄]
        C4[AI 摘要生成]
        C5[檔案管理]
        C6[狀態追蹤]
    end
    
    subgraph "安全機制"
        D1[通行碼驗證]
        D2[IP 封鎖系統]
        D3[嘗試次數限制]
        D4[管理員介面]
    end
    
    subgraph "通知系統"
        E1[Telegram 通知]
        E2[即時狀態更新]
        E3[處理進度回報]
    end
    
    subgraph "資料管理"
        F1[音檔自動清理]
        F2[日誌持久化]
        F3[摘要格式化]
        F4[快取管理]
    end
    
    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B1
    A5 --> B2
    A6 --> B2
    B1 --> C1
    B2 --> C6
    B3 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> C4
    C4 --> C5
    C1 --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    C4 --> E1
    C6 --> E2
    C6 --> E3
    C2 --> F1
    E2 --> F2
    C4 --> F3
    C5 --> F4
```

## 資料流程圖

```mermaid
sequenceDiagram
    participant User as 使用者
    participant Web as Web 介面
    participant API as REST API
    participant Queue as 任務佇列
    participant Worker as 背景工作程序
    participant YouTube as YouTube
    participant Whisper as Whisper 模型
    participant OpenAI as OpenAI API
    participant Telegram as Telegram Bot
    participant Storage as 檔案儲存
    
    User->>Web: 輸入 YouTube URL + 通行碼
    Web->>API: 發送處理請求
    API->>API: 檢查伺服器狀態
    
    alt 伺服器忙碌
        API->>Web: 回覆 busy 狀態
        Web->>User: 顯示忙碌訊息
    else 伺服器空閒
        API->>Queue: 加入任務佇列
        API->>Web: 回覆 processing 狀態
        Web->>User: 顯示處理中
        
        Queue->>Worker: 取出任務
        Worker->>YouTube: 下載音檔
        YouTube->>Worker: 回傳音檔
        Worker->>Storage: 儲存音檔
        
        Worker->>Whisper: 轉錄音檔
        Whisper->>Worker: 回傳字幕
        Worker->>Storage: 儲存字幕檔
        
        Worker->>OpenAI: 生成摘要
        OpenAI->>Worker: 回傳摘要
        Worker->>Storage: 儲存摘要檔
        
        Worker->>Telegram: 發送完成通知
        Worker->>Storage: 刪除音檔
        Worker->>Web: 更新完成狀態
        Web->>User: 顯示完成訊息
    end
```

## 技術架構圖

```mermaid
graph TB
    subgraph "技術棧"
        T1[Python 3.12]
        T2[Flask Web Framework]
        T3[Socket.IO]
        T4[Faster Whisper]
        T5[PyTorch + CUDA]
        T6[OpenAI API]
        T7[yt-dlp]
        T8[Telegram Bot API]
    end
    
    subgraph "部署架構"
        D1[主程序 - Flask Server]
        D2[背景程序 - Worker Process]
        D3[佇列監聽器 - Queue Listener]
        D4[多執行緒 - Socket.IO]
    end
    
    subgraph "資料夾結構"
        F1[downloads/ - 音檔]
        F2[subtitles/ - 字幕]
        F3[summaries/ - 摘要]
        F4[logs/ - 日誌]
        F5[templates/ - HTML]
        F6[static/ - CSS/JS]
    end
    
    T1 --> T2
    T2 --> T3
    T1 --> T4
    T4 --> T5
    T1 --> T6
    T1 --> T7
    T1 --> T8
    
    T2 --> D1
    T1 --> D2
    T1 --> D3
    T3 --> D4
    
    D2 --> F1
    D2 --> F2
    D2 --> F3
    D1 --> F4
    D1 --> F5
    D1 --> F6
```

## 狀態管理圖

```mermaid
stateDiagram-v2
    [*] --> 空閒狀態
    
    空閒狀態 --> 接收請求: 收到 YouTube URL
    接收請求 --> 驗證通行碼: 檢查格式
    
    驗證通行碼 --> 空閒狀態: 通行碼錯誤
    驗證通行碼 --> 加入佇列: 通行碼正確
    
    加入佇列 --> 忙碌狀態: 開始處理
    忙碌狀態 --> 下載音檔: 執行任務
    
    下載音檔 --> 轉錄音檔: 下載完成
    下載音檔 --> 忙碌狀態: 下載失敗
    
    轉錄音檔 --> 生成摘要: 轉錄完成
    轉錄音檔 --> 忙碌狀態: 轉錄失敗
    
    生成摘要 --> 完成處理: 摘要完成
    生成摘要 --> 忙碌狀態: 摘要失敗
    
    完成處理 --> 空閒狀態: 清理資源
    忙碌狀態 --> 空閒狀態: 任務取消
    
    空閒狀態 --> [*]: 程式關閉
```

## 安全架構圖

```mermaid
graph LR
    subgraph "安全層級"
        S1[網路層安全]
        S2[應用層安全]
        S3[資料層安全]
    end
    
    subgraph "安全機制"
        M1[IP 封鎖系統]
        M2[通行碼驗證]
        M3[嘗試次數限制]
        M4[管理員介面]
        M5[檔案路徑驗證]
        M6[輸入驗證]
    end
    
    subgraph "監控機制"
        C1[登入嘗試記錄]
        C2[操作日誌]
        C3[錯誤日誌]
        C4[狀態監控]
    end
    
    S1 --> M1
    S2 --> M2
    S2 --> M3
    S2 --> M4
    S2 --> M6
    S3 --> M5
    
    M1 --> C1
    M2 --> C1
    M3 --> C1
    M4 --> C2
    M5 --> C3
    M6 --> C3
```

## 總結

這個架構圖展示了 Whisper WebApp 的完整功能結構，包括：

1. **多層架構設計**：從外部介面到資料儲存的分層設計
2. **模組化功能**：每個功能模組都有明確的職責
3. **安全機制**：完整的安全驗證和監控系統
4. **可擴展性**：支援多種介面（Web、API、Client）
5. **可靠性**：錯誤處理和狀態管理機制
6. **效能優化**：背景處理和快取機制

整個系統設計注重使用者體驗、安全性和可維護性。 