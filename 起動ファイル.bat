@echo off
chcp 65001
setlocal
:: 実行ファイルの場所（このフォルダ）にカレントディレクトリを移動
cd /d %~dp0

echo 統計解析システムを起動しています...
echo (GPUの初期化に数秒かかる場合があります)
:: --- GTX 950M 用：最新機能の強制無効化 ---
set CUDA_VISIBLE_DEVICES=0
set NVIDIA_TF32_OVERRIDE=0
:: 混合精度演算（AMP）を抑制するための古い形式のフラグ
set TORCH_CUDNN_V8_API_ENABLED=1
:: ---------------------------------------
:: ポータブル環境のPythonを使用してアプリを実行
.\python_env\python.exe .\main.py

if %errorlevel% neq 0 (
    echo.
    echo アプリが異常終了しました。エラー内容を確認してください。
    pause
)
endlocal