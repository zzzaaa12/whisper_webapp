# Whisper WebApp 語音轉文字系統

## 介紹

Whisper WebApp 是一套專為現代影音內容消化、知識整理與自動化而設計的智能音訊處理系統。無論你是學生、研究人員、內容創作者、媒體工作者，還是需要大量處理 YouTube 影片、會議錄音、Podcast 的專業人士，都能透過本系統一鍵將影音內容轉換為結構化文字摘要，快速掌握重點、提升效率。

本專案結合 OpenAI Whisper 語音辨識與 GPT 智能摘要技術，支援多語言（中、英、混合）、GPU 加速、即時進度回報，並提供美觀易用的網頁介面、完整 API 及 Python 自動化工具。你可以用於：

- 快速整理課程、演講、會議、Podcast 內容
- 產生影片字幕與重點摘要，提升 SEO 與內容再利用
- 研究資料、新聞、專題內容的自動化彙整
- 企業內部知識管理、客戶回饋自動彙整

**本專案由 [Cursor](https://www.cursor.so/) + Claude Sonnet 4 AI 協作製作，結合最先進的 AI 編輯與協作體驗。**

---

## 主要功能

### 🎬 核心處理功能
- **YouTube 影片一鍵轉文字與摘要**
- **本地檔案上傳處理**：支援音訊、影片檔案直接上傳
- **AI 驅動語音辨識與重點摘要**（支援中英混合）
- **自動產生 .srt 字幕檔與 .txt 摘要檔**

### 📱 Web 介面功能
- **任務佇列系統**：智能排程任務，支援同時接受多個請求
- **即時處理監控**：即時日誌、進度顯示、取消任務
- **佇列管理介面**：查看任務狀態、佇列位置、處理進度
- **摘要管理系統**：搜尋、書籤、回收桶、批次操作
- **檔案上傳介面**：拖拽上傳、進度顯示、格式驗證
- **響應式設計**：支援桌面和行動裝置

### 🔧 管理與安全功能
- **完整書籤系統**：收藏重要摘要，快速存取
- **智能回收桶**：誤刪檔案可還原，支援永久刪除
- **安全機制**：通行碼保護、IP 限制、登入嘗試管理
- **配置狀態檢查**：自動檢測並警告缺失的配置
- **統一AI摘要服務**：一致的摘要格式與品質保證

### 🚀 API 與自動化
- **完整 REST API**：支援所有功能的程式化操作
- **Python Client**：命令列工具與批次處理
- **Telegram 通知**（選用）

---

## 快速開始

### 安裝與設定

1. **Python 3.8+**（建議 3.10 以上）
2. **安裝依賴**：
```bash
pip install -r requirements.txt
```

3. **建立設定檔**：
複製 `config.example.json` 為 `config.json`，並填入你的金鑰與設定：

```json
{
  "SECRET_KEY": "請填入一組隨機字串",
  "ACCESS_CODE": "你的通行碼（建議設定以提升安全性）",
  "OPENAI_API_KEY": "你的 OpenAI API 金鑰",
  "TELEGRAM_BOT_TOKEN": "你的 Telegram Bot Token（如需通知功能）",
  "TELEGRAM_CHAT_ID": "你的 Telegram Chat ID（如需通知功能）",
  "SERVER_PORT": 5000,
  "OPENAI_MAX_TOKENS": 10000
}
```

4. **啟動系統**：
```bash
python app.py
```

啟動後，請在瀏覽器開啟 [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 使用方式

### Web 介面操作

1. **YouTube 影片處理**：
   - 在首頁輸入 YouTube 連結與通行碼
   - 點擊「開始處理」，系統會智能判斷佇列狀況
   - 第1位立即處理，其他任務排隊等待
   - 即時查看處理進度和日誌

2. **檔案上傳處理**：
   - 點擊「選擇檔案」或直接拖拽音訊/影片檔案
   - 支援 MP3、MP4、WAV、M4A 等常見格式
   - 檔案會自動加入佇列進行語音辨識和摘要生成
   - 智能提示當前佇列位置和預計處理時間

3. **任務佇列管理**：
   - **佇列頁面**：`/queue` - 查看所有任務狀態和進度
   - **實時更新**：自動刷新任務狀態，無需手動重整
   - **任務控制**：取消排隊中的任務，查看詳細資訊
   - **狀態監控**：區分排隊中、處理中、已完成、失敗等狀態

4. **摘要管理**：
   - **摘要列表**：查看所有處理過的摘要，支援搜尋和排序
   - **書籤功能**：將重要摘要加入書籤，方便日後查找
   - **回收桶**：誤刪的檔案可以還原，也可永久刪除
   - **統一格式**：所有摘要採用台灣用語，以【影片內容摘要】開頭

### API 使用

詳細的 API 說明請參考 [README_API.md](README_API.md)

**基本 API 端點**：
- `POST /api/process` - 處理 YouTube 影片（自動加入佇列）
- `POST /api/upload_subtitle` - 上傳字幕檔案
- `POST /api/upload_media` - 上傳媒體檔案（自動加入佇列）
- `GET /api/queue/status` - 獲取佇列狀態
- `GET /api/queue/list` - 獲取任務列表
- `POST /api/queue/cancel` - 取消佇列任務
- `GET /api/bookmarks/list` - 獲取書籤列表
- `GET /api/trash/list` - 獲取回收桶列表

**Python Client 範例**：
```python
from client import WhisperClient

client = WhisperClient("http://localhost:5000")
result = client.send_youtube_url("https://www.youtube.com/watch?v=xxxx")
print(result)
```

---

## 部署選項

### 本地部署

適合開發環境或個人使用：

```bash
python app.py
```

### 生產環境部署

建議使用 Gunicorn 或 uWSGI：

```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 app:app
```

---

## 配置說明

建立 `config.json` 檔案（可參考 `config.example.json`）：
```json
{
  "ACCESS_CODE": "your_access_code",
  "OPENAI_API_KEY": "your_openai_api_key"
}
```

**重要配置項目**：
- `ACCESS_CODE`：通行碼，建議設定以提升安全性
- `OPENAI_API_KEY`：OpenAI API 金鑰，用於 AI 摘要功能
- `TELEGRAM_BOT_TOKEN`：Telegram 機器人 Token（選用）
- `TELEGRAM_CHAT_ID`：Telegram 聊天 ID（選用）

---

## 特色與優勢

- **🚀 高效處理**：GPU 加速，處理速度快，支援任務佇列
- **🌍 多語言支援**：自動辨識中英混合內容
- **🎯 智能摘要**：統一摘要服務，台灣用語，格式一致
- **⚡ 任務佇列**：同時接受多個請求，智能排程處理
- **📊 即時監控**：佇列管理頁面，實時狀態更新
- **📁 完整管理**：檔案管理、書籤、回收桶系統
- **🔒 安全可靠**：通行碼保護、IP 限制、安全標頭
- **🔧 易於整合**：完整 API 支援自動化應用
- **📱 響應式介面**：支援各種螢幕尺寸

---

## 系統需求

**最低需求**：
- Python 3.8+
- 2GB RAM
- 5GB 可用空間

**建議配置**：
- Python 3.10+
- 8GB RAM
- NVIDIA GPU（支援 CUDA）或 Apple Silicon (M1/M2/M3) 以啟用 MLX 加速
- 20GB 可用空間

**支援的檔案格式**：
- **音訊**：MP3, WAV, M4A, AAC, FLAC
- **影片**：MP4, AVI, MOV, MKV, WEBM
- **字幕**：SRT, TXT, VTT

---

## 常見問題

**Q: 如何設定 OpenAI API 金鑰？**
A: 在 `config.json` 中設定 `OPENAI_API_KEY`。

**Q: 支援哪些語言？**
A: 支援 Whisper 所有語言，包括中文、英文、日文等 99 種語言。

**Q: 可以處理多長的音訊？**
A: 理論上沒有長度限制，但建議單個檔案不超過 2 小時。

**Q: 如何啟用 GPU 加速？**
A: 安裝 CUDA 和對應的 PyTorch 版本，系統會自動偵測並使用 GPU。

**Q: 我使用 Apple Silicon Mac，需要額外設定嗎？**
A: 不需要。系統會自動偵測 Apple Silicon，並改用 `mlx-community/whisper-large-v3-turbo-q4` 模型與 MLX 推論引擎。首次轉錄時會自動下載模型，若未安裝請執行 `pip install mlx-whisper` 以取得必要套件。若 MLX 環境啟動失敗，任務會直接標記為失敗，請依錯誤訊息檢查 MLX 安裝或系統設定。

---

## 貢獻與支援

- **GitHub**：[https://github.com/zzzaaa12/whisper_webapp](https://github.com/zzzaaa12/whisper_webapp)
- **問題回報**：請在 GitHub Issues 提出
- **功能建議**：歡迎提交 Pull Request
- **聯絡信箱**：zzzaaa12@gmail.com

---

## 授權

本專案採用 MIT License，歡迎自由使用與貢獻。
