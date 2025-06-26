# Whisper WebApp 語音轉文字系統

## 介紹

Whisper WebApp 是一套專為現代影音內容消化、知識整理與自動化而設計的智能音訊處理系統。無論你是學生、研究人員、內容創作者、媒體工作者，還是需要大量處理 YouTube 影片、會議錄音、Podcast 的專業人士，都能透過本系統一鍵將影音內容轉換為結構化文字摘要，快速掌握重點、提升效率。

本專案結合 OpenAI Whisper 語音辨識與 GPT 智能摘要技術，支援多語言（中、英、混合）、GPU 加速、即時進度回報，並提供美觀易用的網頁介面、API 及 Python 自動化工具。你可以用於：

- 快速整理課程、演講、會議、Podcast 內容
- 產生影片字幕與重點摘要，提升 SEO 與內容再利用
- 研究資料、新聞、專題內容的自動化彙整
- 企業內部知識管理、客戶回饋自動彙整

**本專案由 [Cursor](https://www.cursor.so/) + Claude Sonnet 4 AI 協作製作，結合最先進的 AI 編輯與協作體驗。**

---

## 主要功能

- 🎬 **YouTube 影片一鍵轉文字與摘要**
- 🤖 **AI 驅動語音辨識與重點摘要**（支援中英混合）
- 📝 **自動產生 .srt 字幕檔與 .txt 摘要檔**
- 📱 **Web 前端介面**：即時日誌、進度顯示、取消任務
- 🗂️ **摘要管理**：搜尋、書籤、回收桶、批次操作
- 🔔 **Telegram 通知**（選用）
- 🛡️ **安全機制**：通行碼、IP 限制、登入嘗試管理
- 🧩 **Python API 與命令列工具**

---

## 安裝與環境需求

1. **Python 3.8+**（建議 3.10 以上）
2. **安裝依賴**：

```bash
pip install -r requirements.txt
```

3. **建立設定檔**：

請複製 `config.example.json` 為 `config.json`，並填入你的金鑰與設定：

```json
{
  "SECRET_KEY": "請填入一組隨機字串",
  "OPENAI_API_KEY": "你的 OpenAI API 金鑰",
  "TELEGRAM_BOT_TOKEN": "你的 Telegram Bot Token（如需通知功能）",
  "TELEGRAM_CHAT_ID": "你的 Telegram Chat ID（如需通知功能）",
  "SERVER_PORT": 5000
}
```

> `config.json` 已自動加入 `.gitignore`，不會被上傳。

---

## 啟動方式

```bash
python app.py
```

啟動後，請在瀏覽器開啟 [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 前端主要功能

- **首頁**：輸入 YouTube 連結與通行碼，一鍵開始處理
- **即時日誌**：顯示處理進度、錯誤、狀態
- **摘要管理**：
  - 查看所有摘要、搜尋、批次刪除、加入書籤
  - 書籤頁：快速存取重要摘要
  - 回收桶：可還原或永久刪除檔案
- **摘要詳情**：檢視單一摘要內容
- **管理員介面**：登入嘗試紀錄、IP 封鎖狀態

---

## API 與 Python Client

### REST API

- **POST /api/process**
  - 輸入：`{"youtube_url": "https://www.youtube.com/watch?v=xxxx"}`
  - 回傳：處理狀態、任務 ID、錯誤訊息等

### Python Client

```python
from client import WhisperClient
client = WhisperClient("http://localhost:5000")
result = client.send_youtube_url("https://www.youtube.com/watch?v=xxxx")
print(result)
```

- 支援批次處理、狀態監控、錯誤重試，詳見 `README_API.md`

---

## 典型流程

1. 輸入 YouTube 連結與通行碼，送出任務
2. 系統自動下載音訊、語音辨識、AI 摘要
3. 即時顯示進度與日誌
4. 處理完成後可下載字幕與摘要，或由 Telegram 通知
5. 可於摘要管理頁搜尋、書籤、刪除、還原

---

## 特色與優勢

- GPU 加速，處理速度快
- 多語言自動辨識
- 結構化摘要，重點不遺漏
- 完整檔案管理與安全機制
- 支援 API 與自動化

---

## 授權

本專案採用 MIT License，歡迎自由使用與貢獻。 