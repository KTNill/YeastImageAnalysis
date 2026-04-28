@echo off
chcp 65001
setlocal
:: 実行ファイルの場所（このフォルダ）にカレントディレクトリを移動
cd /d %~dp0

echo 統計解析システムを起動しています...
echo (GPUの初期化に数秒かかる場合があります)

:: ポータブル環境のPythonを使用してアプリを実行
.\python_env\python.exe .\app\main.py

if %errorlevel% neq 0 (
    echo.
    echo アプリが異常終了しました。エラー内容を確認してください。
    pause
)
endlocal