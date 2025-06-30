@echo off
echo 正在安裝 Whisper WebApp 的GPU加速版本...
echo.

echo [1/3] 檢查Python環境...
python --version
if %errorlevel% neq 0 (
    echo 錯誤: 找不到Python，請先安裝Python 3.8+
    pause
    exit /b 1
)

echo.
echo [2/3] 安裝CUDA版本的PyTorch (支援NVIDIA GPU)...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
if %errorlevel% neq 0 (
    echo 警告: CUDA版本PyTorch安裝失敗，將安裝CPU版本
    pip install torch torchaudio
)

echo.
echo [3/3] 安裝其他依賴套件...
pip install -r requirements.txt

echo.
echo [測試] 檢查GPU支援...
python -c "import torch; print('PyTorch版本:', torch.__version__); print('CUDA可用:', torch.cuda.is_available()); print('GPU數量:', torch.cuda.device_count() if torch.cuda.is_available() else 0)"

echo.
echo 安裝完成！
if exist config.example.json (
    echo 請複製 config.example.json 為 config.json 並設定您的API金鑰
)
echo 運行 python app.py 來啟動服務
pause