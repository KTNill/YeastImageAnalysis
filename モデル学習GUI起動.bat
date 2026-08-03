@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ==================================================
REM Cellpose GUI Launcher (For custom model training)
REM ==================================================
echo [INFO] Starting Cellpose Annotation and Training GUI...
echo.

if not exist "%~dp0python_env\python.exe" (
    echo [ERROR] python_env not found.
    echo [ERROR] Please run "起動ファイル.bat" first to setup the environment.
    pause
    exit /b 1
)

REM --- Check GUI dependencies (qtpy) and install if missing ---
"%~dp0python_env\python.exe" -c "import qtpy" >nul 2>&1
if errorlevel 1 (
    echo [INFO] GUI dependencies are missing. Installing now...
    echo [INFO] This will only happen once and may take a minute.

    "%~dp0python_env\python.exe" -m pip install "cellpose[gui]"

    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install GUI dependencies.
        pause
        exit /b 1
    )
    echo [SUCCESS] GUI dependencies installed successfully.
    echo.
)

echo [INFO] Launching Cellpose GUI...
echo [INFO] (GPU initialization may take a few seconds)
echo [INFO] Please do not close this black window while the GUI is running.
echo.

REM --- GTX 950M Override Flags ---
set CUDA_VISIBLE_DEVICES=0
set NVIDIA_TF32_OVERRIDE=0
set TORCH_CUDNN_V8_API_ENABLED=1
REM --------------------------------

"%~dp0python_env\python.exe" -m cellpose

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Cellpose GUI exited abnormally.
    pause
)

endlocal