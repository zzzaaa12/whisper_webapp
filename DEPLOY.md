# 🚀 Whisper WebApp 部署指南

降低部署門檻的多種方式，選擇最適合你的！

## 🎯 快速開始（推薦新手）

### Docker 一鍵部署 ⭐⭐⭐⭐⭐

**Windows 用戶：**
```bash
# 1. 下載專案
git clone https://github.com/zzzaaa12/whisper_webapp.git
cd whisper_webapp

# 2. 雙擊執行
deploy.bat
```

**Linux/Mac 用戶：**
```bash
# 1. 下載專案
git clone https://github.com/zzzaaa12/whisper_webapp.git
cd whisper_webapp

# 2. 執行部署腳本
chmod +x deploy.sh
./deploy.sh
```

**就這樣！** 🎉 腳本會自動：
- ✅ 檢查 Docker 環境
- ✅ 創建必要目錄
- ✅ 複製配置範例
- ✅ 建構並啟動服務
- ✅ 開啟瀏覽器

---

## 🔧 環境需求

### 最低需求
- **Docker Desktop** （包含 Docker Compose）
- **2GB RAM**
- **5GB 可用空間**

### 安裝 Docker
- **Windows**: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Mac**: [Docker Desktop](https://www.docker.com/products/docker-desktop)  
- **Linux**: [Docker Engine](https://docs.docker.com/engine/install/)

---

## ⚙️ 配置設定

### 必要設定
只需在 `.env` 檔案中設定：
```bash
OPENAI_API_KEY=sk-your-api-key-here
```

### 可選設定
```bash
ACCESS_CODE=your-password        # 存取密碼（建議設定）
SECRET_KEY=random-secret-key     # Flask 密鑰
TELEGRAM_BOT_TOKEN=xxx           # Telegram 通知（可選）
TELEGRAM_CHAT_ID=xxx             # Telegram 通知（可選）
```

---

## 🎮 使用方式

### 啟動服務
```bash
docker-compose up -d
```

### 訪問網站
開啟瀏覽器：http://localhost:5000

### 查看日誌
```bash
docker-compose logs -f
```

### 停止服務
```bash
docker-compose down
```

---

## 🔄 傳統安裝方式

如果不想用 Docker：

### 1. 安裝 Python 3.8+
```bash
python --version  # 確認版本
```

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 設定配置
```bash
cp config.example.json config.json
# 編輯 config.json 填入 API Key
```

### 4. 啟動
```bash
python app.py
```

---

## 🛠️ 進階部署

### GPU 支援
```bash
# 使用 GPU 版本（需要 NVIDIA Docker）
docker-compose --profile gpu up -d
```

### 雲端部署
- **Railway**: 一鍵部署到雲端
- **Heroku**: 支援 Container 部署
- **DigitalOcean**: App Platform 部署
- **AWS**: ECS/EKS 部署

### 反向代理
```nginx
# Nginx 配置範例
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 🐛 常見問題

### Q: Docker 建構失敗？
```bash
# 清除快取重新建構
docker-compose build --no-cache
```

### Q: 連接埠被佔用？
```bash
# 修改 docker-compose.yml 中的連接埠
ports:
  - "5001:5000"  # 改用 5001
```

### Q: GPU 不工作？
確保安裝了 NVIDIA Docker：
```bash
# Ubuntu
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker
```

---

## 📞 支援

- 🐛 **問題回報**: [GitHub Issues](https://github.com/zzzaaa12/whisper_webapp/issues)
- 💬 **討論**: [GitHub Discussions](https://github.com/zzzaaa12/whisper_webapp/discussions)
- 📧 **聯絡**: zzzaaa12@gmail.com

---

## 🎯 總結

| 方式 | 難度 | 時間 | 推薦度 |
|------|------|------|--------|
| Docker 一鍵部署 | ⭐ | 5分鐘 | ⭐⭐⭐⭐⭐ |
| 傳統 Python 安裝 | ⭐⭐⭐ | 15分鐘 | ⭐⭐⭐ |
| 雲端部署 | ⭐⭐ | 10分鐘 | ⭐⭐⭐⭐ |

**新手建議：直接使用 Docker 一鍵部署！** 🚀 