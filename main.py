# YeastImageAnalysis
# Copyright (c) 2026 KT Nill
# This program is free software under the terms of the GNU GPL v3.

import logging
import os
import sys
import datetime
from app.utils.config_loader import ConfigLoader
from app.gui.app_window import App


def setup_logging():
    """ログ設定：コンソールとlogsフォルダ内のファイルの両方に出力する"""
    log_dir = "logs"

    # 1. logsフォルダがなければ作成する
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 実行日の名前でログファイル名を決定 (例: analysis_20240520.log)
    log_filename = f"analysis_{datetime.datetime.now().strftime('%Y%m%d')}.log"
    log_path = os.path.join(log_dir, log_filename)

    # 3. ログの出力先を設定 (ファイルとコンソールの両方)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),  # ファイルへ
            logging.StreamHandler(sys.stdout)  # コンソールへ
        ]
    )


def main():
    # ログの初期化を最初に実行
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("アプリケーションを起動しました。")

    # 設定ディレクトリの指定 (フォルダ内の複数CSVを監視・読込)
    config_dir = os.path.join("config")
    config = ConfigLoader(config_dir)

    # GUIのインスタンスを作成
    app = App()
    app.config_data = config  # Configを先に渡す
    app.setup_ui()  # その後にUIを組み立てる

    # メインループの実行
    app.mainloop()


if __name__ == "__main__":
    main()
