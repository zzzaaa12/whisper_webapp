# 使用官方 Python 3.10 基礎映像
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 創建必要的目錄
RUN mkdir -p logs subtitles summaries downloads trash/subtitles trash/summaries

# 暴露端口
EXPOSE 5000

# 設定環境變數
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# 啟動命令
CMD ["python", "app.py"] 