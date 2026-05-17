#!/bin/bash
# 実行ファイルのある場所にカレントディレクトリを移動
cd "$(dirname "$0")"

echo "========================================="
echo " 統計解析システム (Mac版) を起動しています"
echo "========================================="

# 仮想環境(venv)が存在しない場合は初回セットアップを実行
if [ ! -d "venv" ]; then
    echo "初回起動を検知しました。解析環境を構築しています（数分かかります）..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip

    # Mac(MPS/CPU)用のPyTorchと、V4モデル互換のNumpy1系をインストール
    pip install torch torchvision
    pip install cellpose customtkinter pandas opencv-python scikit-image scipy numba pyyaml darkdetect openpyxl "numpy<2"
    echo "環境構築が完了しました。"
else
    # 2回目以降は環境を有効化するだけ
    source venv/bin/activate
fi

# アプリケーションの実行
python3 main.py

# アプリ終了時にターミナルが勝手に閉じないようにする
echo ""
echo "アプリケーションが終了しました。このウィンドウを閉じてください。"
read -p "Press [Enter] key to continue..."