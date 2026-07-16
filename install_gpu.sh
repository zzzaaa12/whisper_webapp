#!/bin/bash
set -e

echo "Installing Whisper WebApp GPU dependencies..."
echo

echo "[1/3] Checking Python..."
python3 --version

echo
echo "[2/3] Installing requirements with CUDA PyTorch wheels..."
python3 -m pip install --force-reinstall -r requirements.txt

echo
echo "[3/3] Verifying CUDA availability..."
python3 -c "import sys, torch; print('Python:', sys.executable); print('PyTorch:', torch.__version__); print('CUDA runtime:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU count:', torch.cuda.device_count()); print('GPU 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo
echo "Installation complete."
