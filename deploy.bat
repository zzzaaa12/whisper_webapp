@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ===========================================
REM Whisper WebApp Windows 一鍵部署腳本
REM ===========================================

echo 🚀 開始部署 Whisper WebApp...

REM 檢查 Docker 是否安裝
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 錯誤：請先安裝 Docker Desktop
    echo 下載網址：https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM 檢查 Docker Compose 是否可用
docker-compose --version >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo ❌ 錯誤：請先安裝 Docker Compose
        pause
        exit /b 1
    )
)

REM 創建必要目錄
echo 📁 創建必要目錄...
if not exist "data" mkdir data
if not exist "data\logs" mkdir data\logs
if not exist "data\subtitles" mkdir data\subtitles
if not exist "data\summaries" mkdir data\summaries
if not exist "data\downloads" mkdir data\downloads
if not exist "data\trash" mkdir data\trash
if not exist "data\trash\subtitles" mkdir data\trash\subtitles
if not exist "data\trash\summaries" mkdir data\trash\summaries

REM 檢查配置檔案
if not exist ".env" (
    echo ⚠️  未找到 .env 檔案，複製範例檔案...
    if exist "env.example" (
        copy env.example .env >nul
        echo ✅ 已複製 env.example 為 .env
        echo ⚠️  請編輯 .env 檔案填入你的 API Key！
        echo    至少需要設定 OPENAI_API_KEY
    ) else (
        echo ❌ 未找到 env.example 檔案
        pause
        exit /b 1
    )
)

REM 檢查是否有設定 OPENAI_API_KEY
findstr /C:"OPENAI_API_KEY=sk-" .env >nul 2>&1
if errorlevel 1 (
    echo ⚠️  警告：請在 .env 檔案中設定你的 OPENAI_API_KEY
    echo    格式：OPENAI_API_KEY=sk-your-api-key-here
)

REM 建構 Docker 映像
echo 🔨 建構 Docker 映像...
docker-compose build
if errorlevel 1 (
    echo ❌ 建構失敗
    pause
    exit /b 1
)

REM 啟動服務
echo 🚀 啟動服務...
docker-compose up -d
if errorlevel 1 (
    echo ❌ 啟動失敗
    pause
    exit /b 1
)

REM 等待服務啟動
echo ⏳ 等待服務啟動...
timeout /t 5 /nobreak >nul

REM 檢查服務狀態
docker-compose ps | findstr "Up" >nul
if not errorlevel 1 (
    echo ✅ 部署成功！
    echo.
    echo 🌐 請開啟瀏覽器訪問：http://localhost:5000
    echo 📋 查看服務狀態：docker-compose ps
    echo 📜 查看日誌：docker-compose logs -f
    echo 🛑 停止服務：docker-compose down
    echo.
    echo ⚠️  提醒：
    echo    - 請確保已在 .env 檔案中設定 OPENAI_API_KEY
    echo    - 建議設定 ACCESS_CODE 提升安全性
    echo.
    echo 按任意鍵開啟瀏覽器...
    pause >nul
    start http://localhost:5000
) else (
    echo ❌ 部署失敗，請檢查日誌：docker-compose logs
    pause
    exit /b 1
) 