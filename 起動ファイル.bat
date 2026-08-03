@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ==================================================
REM Google Drive Settings
REM ==================================================
set "PYTHON_ENV_FILE_ID=https://drive.google.com/file/d/1FgzL3hbGCw8A8CmgOBdbmU6Q2FyisFD1/view?usp=drive_link"

set "MODEL1_NAME=custom_cpsam_v1"
set "MODEL1_FILE_ID=https://drive.google.com/file/d/1X09CtPsMeajxPSDlDFZGl2Wpy6IYbSo5/view?usp=drive_link"

set "MODEL2_NAME=custom_cpsam_liqid_v4"
set "MODEL2_FILE_ID=https://drive.google.com/file/d/1ibG7JEUxcQi5OmOEXIrs1Xtlczsz9Yl6/view?usp=drive_link"


REM ==================================================
REM 1. Check and Download python_env
REM ==================================================
if exist "%~dp0python_env\python.exe" goto :CHECK_MODELS

echo [INFO] python_env not found.
echo [INFO] Downloading python_env.zip from Google Drive...
echo.

call :DOWNLOAD_FILE "%PYTHON_ENV_FILE_ID%" "python_env_temp.zip"

if not exist "python_env_temp.zip" (
    echo [ERROR] Download failed. Check your network or Google Drive link.
    pause
    exit /b 1
)

REM Verify file is not empty
for %%I in (python_env_temp.zip) do if %%~zI EQU 0 (
    echo.
    echo [ERROR] Downloaded file is empty.
    echo [ERROR] Please check Google Drive sharing settings.
    del /f /q python_env_temp.zip
    echo.
    pause
    exit /b 1
)

echo [INFO] Extracting python_env.zip...
mkdir "temp_env"
tar -xf "python_env_temp.zip" -C "temp_env" >NUL 2>&1
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'python_env_temp.zip' -DestinationPath 'temp_env' -Force"
)

echo [INFO] Moving files...
if exist "temp_env\python_env" (
    move "temp_env\python_env" "python_env" >NUL
) else (
    move "temp_env" "python_env" >NUL
)

if exist "python_env_temp.zip" del /f /q "python_env_temp.zip"
if exist "temp_env" rmdir /s /q "temp_env"

if not exist "%~dp0python_env\python.exe" (
    echo [ERROR] Failed to locate python_env\python.exe after extraction.
    pause
    exit /b 1
)
echo [SUCCESS] python_env setup completed successfully.
echo.


:CHECK_MODELS
REM ==================================================
REM 2. Check and Download models
REM ==================================================
if exist "%~dp0models" goto :LAUNCH_APP

echo [INFO] models folder not found.
echo [INFO] Downloading initial model files...
echo.
mkdir "models"

if not "%MODEL1_FILE_ID%"=="" (
    echo [INFO] Downloading %MODEL1_NAME%...
    call :DOWNLOAD_FILE "%MODEL1_FILE_ID%" "models\%MODEL1_NAME%"
)

if not "%MODEL2_FILE_ID%"=="" (
    echo [INFO] Downloading %MODEL2_NAME%...
    call :DOWNLOAD_FILE "%MODEL2_FILE_ID%" "models\%MODEL2_NAME%"
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

REM --- GTX 950M Override Flags ---
set CUDA_VISIBLE_DEVICES=0
set NVIDIA_TF32_OVERRIDE=0
set TORCH_CUDNN_V8_API_ENABLED=1
REM --------------------------------

"%~dp0python_env\python.exe" "%~dp0main.py"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited abnormally.
    pause
)

exit /b 0


REM ==================================================
REM Helper Subroutine: Download File via Windows curl
REM ==================================================
:DOWNLOAD_FILE
set "URL_INPUT=%~1"
set "OUT_INPUT=%~2"

REM Extract Google Drive File ID automatically
set "TMP_ID=!URL_INPUT:*file/d/=!"
for /f "delims=/?" %%A in ("!TMP_ID!") do set "EXTRACTED_ID=%%A"

REM Download using Windows built-in curl.exe
curl.exe -L -f -o "%OUT_INPUT%" "https://drive.usercontent.google.com/download?id=!EXTRACTED_ID!&export=download&confirm=t"
exit /b 0