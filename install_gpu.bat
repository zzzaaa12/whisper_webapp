@echo off
setlocal

echo Installing Whisper WebApp GPU dependencies...
echo.

echo [1/3] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python was not found.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing requirements with CUDA PyTorch wheels...
python -m pip install --force-reinstall -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Dependency installation failed. CPU fallback is disabled.
    pause
    exit /b 1
)

echo.
echo [3/3] Verifying CUDA availability...
python -c "import torch; print('Python:', __import__('sys').executable); print('PyTorch:', torch.__version__); print('CUDA runtime:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU count:', torch.cuda.device_count()); print('GPU 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
if %errorlevel% neq 0 (
    echo ERROR: CUDA verification failed.
    pause
    exit /b 1
)

echo.
echo Installation complete.
pause
