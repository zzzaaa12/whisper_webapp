#!/bin/bash

# ===========================================
# Whisper WebApp 一鍵部署腳本
# ===========================================

set -e  # 如果任何命令失敗就退出

echo "🚀 開始部署 Whisper WebApp..."

# 檢查 Docker 是否安裝
if ! command -v docker &> /dev/null; then
    echo "❌ 錯誤：請先安裝 Docker"
    echo "安裝指引：https://docs.docker.com/get-docker/"
    exit 1
fi

# 檢查 Docker Compose 是否安裝
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ 錯誤：請先安裝 Docker Compose"
    echo "安裝指引：https://docs.docker.com/compose/install/"
    exit 1
fi

# 創建必要目錄
echo "📁 創建必要目錄..."
mkdir -p data/{logs,subtitles,summaries,downloads,trash/subtitles,trash/summaries}

# 檢查配置檔案
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 檔案，複製範例檔案..."
    if [ -f "env.example" ]; then
        cp env.example .env
        echo "✅ 已複製 env.example 為 .env"
        echo "⚠️  請編輯 .env 檔案填入你的 API Key！"
        echo "   至少需要設定 OPENAI_API_KEY"
    else
        echo "❌ 未找到 env.example 檔案"
        exit 1
    fi
fi

# 檢查是否有設定 OPENAI_API_KEY
if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null; then
    echo "⚠️  警告：請在 .env 檔案中設定你的 OPENAI_API_KEY"
    echo "   格式：OPENAI_API_KEY=sk-your-api-key-here"
fi

# 建構 Docker 映像
echo "🔨 建構 Docker 映像..."
docker-compose build

# 啟動服務
echo "🚀 啟動服務..."
docker-compose up -d

# 等待服務啟動
echo "⏳ 等待服務啟動..."
sleep 5

# 檢查服務狀態
if docker-compose ps | grep -q "Up"; then
    echo "✅ 部署成功！"
    echo ""
    echo "🌐 請開啟瀏覽器訪問：http://localhost:5000"
    echo "📋 查看服務狀態：docker-compose ps"
    echo "📜 查看日誌：docker-compose logs -f"
    echo "🛑 停止服務：docker-compose down"
    echo ""
    echo "⚠️  提醒："
    echo "   - 請確保已在 .env 檔案中設定 OPENAI_API_KEY"
    echo "   - 建議設定 ACCESS_CODE 提升安全性"
else
    echo "❌ 部署失敗，請檢查日誌：docker-compose logs"
    exit 1
fi 