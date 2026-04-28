import logging
import os
import sys
import datetime
from utils.config_loader import ConfigLoader
from core.analyzer import YeastAnalyzer
from gui.app_window import App

# プロジェクトのルートディレクトリを取得 (appフォルダの1つ上)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def setup_logging():
    """ログ設定：コンソールとlogsフォルダ内のファイルの両方に出力する"""
    log_dir = os.path.join(BASE_DIR, "logs")

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

    # 設定ファイルの読み込み (絶対パスで解決)
    config_path = os.path.join(BASE_DIR, "config", "settings.csv")
    config = ConfigLoader(config_path)

    # GUIのインスタンスを作成
    app = App()
    app.config_data = config

    # 解析エンジンの初期化
    try:
        # ここで再度 logging.basicConfig が呼ばれると設定が上書きされる可能性があるため、
        # analyzer.py 側の logging.basicConfig(level=logging.INFO) は削除することを推奨します。
        analyzer = YeastAnalyzer(config)
        app.analyzer = analyzer
    except Exception as e:
        logger.error(f"解析エンジンの初期化エラー: {e}")
        app.analyzer = None

    # メインループの実行
    app.mainloop()


if __name__ == "__main__":
    main()