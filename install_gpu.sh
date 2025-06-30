#!/bin/bash

echo "正在安裝 Whisper WebApp 的GPU加速版本..."
echo

echo "[1/3] 檢查Python環境..."
python3 --version
if [ $? -ne 0 ]; then
    echo "錯誤: 找不到Python，請先安裝Python 3.8+"
    exit 1
fi

echo
echo "[2/3] 安裝CUDA版本的PyTorch (支援NVIDIA GPU)..."
pip3 install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
if [ $? -ne 0 ]; then
    echo "警告: CUDA版本PyTorch安裝失敗，將安裝CPU版本"
    pip3 install torch torchaudio
fi

echo
echo "[3/3] 安裝其他依賴套件..."
pip3 install -r requirements.txt

echo
echo "[測試] 檢查GPU支援..."
python3 -c "import torch; print('PyTorch版本:', torch.__version__); print('CUDA可用:', torch.cuda.is_available()); print('GPU數量:', torch.cuda.device_count() if torch.cuda.is_available() else 0)"

echo
echo "安裝完成！"
if [ -f "config.example.json" ]; then
    echo "請複製 config.example.json 為 config.json 並設定您的API金鑰"
fi
echo "運行 python3 app.py 來啟動服務"