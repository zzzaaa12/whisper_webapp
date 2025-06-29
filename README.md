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
- **即時處理監控**：即時日誌、進度顯示、取消任務
- **摘要管理系統**：搜尋、書籤、回收桶、批次操作
- **檔案上傳介面**：拖拽上傳、進度顯示、格式驗證
- **響應式設計**：支援桌面和行動裝置

### 🔧 管理與安全功能
- **完整書籤系統**：收藏重要摘要，快速存取
- **智能回收桶**：誤刪檔案可還原，支援永久刪除
- **安全機制**：通行碼保護、IP 限制、登入嘗試管理
- **配置狀態檢查**：自動檢測並警告缺失的配置

### 🚀 API 與自動化
- **完整 REST API**：支援所有功能的程式化操作
- **Python Client**：命令列工具與批次處理
- **Telegram 通知**（選用）
- **Docker 容器化部署**

---

## 快速開始

### 方法一：Docker 部署（推薦）

1. **下載專案**：
```bash
git clone https://github.com/zzzaaa12/whisper_webapp.git
cd whisper_webapp
```

2. **設定環境變數**：
```bash
cp env.example .env
# 編輯 .env 檔案，填入你的 OpenAI API 金鑰和通行碼
```

3. **一鍵啟動**：
```bash
# Linux/Mac
./deploy.sh

# Windows
deploy.bat
```

### 方法二：傳統安裝

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
   - 點擊「開始處理」，系統會自動下載、轉換、摘要
   - 即時查看處理進度和日誌

2. **檔案上傳處理**：
   - 點擊「選擇檔案」或直接拖拽音訊/影片檔案
   - 支援 MP3、MP4、WAV、M4A 等常見格式
   - 檔案會自動進行語音辨識和摘要生成

3. **摘要管理**：
   - **摘要列表**：查看所有處理過的摘要，支援搜尋和排序
   - **書籤功能**：將重要摘要加入書籤，方便日後查找
   - **回收桶**：誤刪的檔案可以還原，也可永久刪除

### API 使用

詳細的 API 說明請參考 [README_API.md](README_API.md)

**基本 API 端點**：
- `POST /api/process` - 處理 YouTube 影片
- `POST /api/upload_subtitle` - 上傳字幕檔案
- `POST /api/upload_media` - 上傳媒體檔案
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

### Docker 部署（推薦）

支援 CPU 和 GPU 兩種模式：

```bash
# CPU 模式
docker-compose up -d

# GPU 模式（需要 NVIDIA Docker）
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### 傳統部署

適合開發環境或需要自訂配置的情況：

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

系統支援兩種配置方式：

### 1. 環境變數配置（推薦）

建立 `.env` 檔案：
```env
ACCESS_CODE=your_access_code
OPENAI_API_KEY=your_openai_api_key
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 2. JSON 配置檔案

建立 `config.json` 檔案：
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

- **🚀 高效處理**：GPU 加速，處理速度快
- **🌍 多語言支援**：自動辨識中英混合內容
- **🎯 智能摘要**：結構化摘要，重點不遺漏
- **📁 完整管理**：檔案管理、書籤、回收桶系統
- **🔒 安全可靠**：通行碼保護、IP 限制、安全標頭
- **🔧 易於整合**：完整 API 支援自動化應用
- **📱 響應式介面**：支援各種螢幕尺寸
- **🐳 容器化部署**：一鍵部署，環境隔離

---

## 系統需求

**最低需求**：
- Python 3.8+
- 2GB RAM
- 5GB 可用空間

**建議配置**：
- Python 3.10+
- 8GB RAM
- NVIDIA GPU（支援 CUDA）
- 20GB 可用空間

**支援的檔案格式**：
- **音訊**：MP3, WAV, M4A, AAC, FLAC
- **影片**：MP4, AVI, MOV, MKV, WEBM
- **字幕**：SRT, TXT, VTT

---

## 常見問題

**Q: 如何設定 OpenAI API 金鑰？**
A: 在 `.env` 檔案或 `config.json` 中設定 `OPENAI_API_KEY`。

**Q: 支援哪些語言？**
A: 支援 Whisper 所有語言，包括中文、英文、日文等 99 種語言。

**Q: 可以處理多長的音訊？**
A: 理論上沒有長度限制，但建議單個檔案不超過 2 小時。

**Q: 如何啟用 GPU 加速？**
A: 安裝 CUDA 和對應的 PyTorch 版本，系統會自動偵測並使用 GPU。

---

## 貢獻與支援

- **GitHub**：[https://github.com/zzzaaa12/whisper_webapp](https://github.com/zzzaaa12/whisper_webapp)
- **問題回報**：請在 GitHub Issues 提出
- **功能建議**：歡迎提交 Pull Request
- **聯絡信箱**：zzzaaa12@gmail.com

---

## 授權

本專案採用 MIT License，歡迎自由使用與貢獻。