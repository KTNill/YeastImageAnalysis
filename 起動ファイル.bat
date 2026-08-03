@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ==================================================
REM Settings
REM ==================================================
REM Official python-build-standalone URL (Python 3.12.5 / x86_64 / Windows / install_only)
set "PYTHON_STANDALONE_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20240814/cpython-3.12.5+20240814-x86_64-pc-windows-msvc-install_only.tar.gz"

REM Hugging Face Model Settings
set "HF_BASE_URL=https://huggingface.co/KTNill/yeast-cellpose-models/resolve/main"
set "MODEL1_NAME=custom_cpsam_v1"
set "MODEL1_URL=%HF_BASE_URL%/custom_cpsam_v1"
set "MODEL2_NAME=custom_cpsam_liqid_v4"
set "MODEL2_URL=%HF_BASE_URL%/custom_cpsam_liqid_v4"


REM ==================================================
REM 1. Check and Download Python Standalone
REM ==================================================
if exist "%~dp0python_env\python.exe" goto :SETUP_ENV_DEPS

echo [INFO] Portable Python environment not found.
echo [INFO] Downloading python-build-standalone (Python 3.12)...
echo.

curl.exe -L -f -o "python_standalone.tar.gz" "%PYTHON_STANDALONE_URL%"

if not exist "python_standalone.tar.gz" (
    echo [ERROR] Download failed. Check your network connection.
    pause
    exit /b 1
)

echo [INFO] Extracting Python environment...
mkdir "temp_env"
tar -xzf "python_standalone.tar.gz" -C "temp_env"

echo [INFO] Setting up python_env directory...
if exist "temp_env\python" (
    move "temp_env\python" "python_env" >NUL
) else (
    move "temp_env" "python_env" >NUL
)

if exist "python_standalone.tar.gz" del /f /q "python_standalone.tar.gz"
if exist "temp_env" rmdir /s /q "temp_env"

if not exist "%~dp0python_env\python.exe" (
    echo [ERROR] Failed to locate python_env\python.exe after extraction.
    pause
    exit /b 1
)
echo [SUCCESS] Standalone Python setup completed.
echo.


:SETUP_ENV_DEPS
REM ==================================================
REM 1.5. Install Pip & Dependencies
REM ==================================================
if exist "%~dp0python_env\Scripts\pip.exe" goto :INSTALL_REQS

echo [INFO] Installing pip...
curl.exe -L -f -o "get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
"%~dp0python_env\python.exe" "get-pip.py"
if exist "get-pip.py" del /f /q "get-pip.py"

:INSTALL_REQS
if not exist "%~dp0requirements.txt" goto :CHECK_MODELS

echo [INFO] Installing / Verifying dependencies from requirements.txt...
"%~dp0python_env\python.exe" -m pip install -r "%~dp0requirements.txt" --extra-index-url https://download.pytorch.org/whl/cu118


:CHECK_MODELS
REM ==================================================
REM 2. Check and Download models
REM ==================================================
if exist "%~dp0models" goto :LAUNCH_APP

echo [INFO] models folder not found.
echo [INFO] Downloading initial model files...
echo.
mkdir "models"

if defined MODEL1_URL (
    echo [INFO] Downloading %MODEL1_NAME%...
    curl.exe -L -f -o "models\%MODEL1_NAME%" "%MODEL1_URL%"
)

if defined MODEL2_URL (
    echo [INFO] Downloading %MODEL2_NAME%...
    curl.exe -L -f -o "models\%MODEL2_NAME%" "%MODEL2_URL%"
)

echo.
echo [SUCCESS] Model files setup completed.
echo.


:LAUNCH_APP
REM ==================================================
REM 3. Launch Application
REM ==================================================
echo [INFO] Starting Yeast Image Analysis System...
echo [INFO] (GPU initialization may take a few seconds)

set "PYTHONPATH=%~dp0"

set CUDA_VISIBLE_DEVICES=0
set NVIDIA_TF32_OVERRIDE=0
set TORCH_CUDNN_V8_API_ENABLED=1

"%~dp0python_env\python.exe" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited abnormally.
    pause
)

exit /b 0