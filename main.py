import logging
from utils.config_loader import ConfigLoader
from core.analyzer import YeastAnalyzer
from gui.app_window import App

def main():
    """メインエントリポイント"""
    logging.basicConfig(level=logging.INFO)

    # 1. 設定ロード
    config = ConfigLoader("config/settings.csv")

    # 2. GUI初期化
    app = App()
    app.config_data = config

    # 3. エンジン初期化
    try:
        analyzer = YeastAnalyzer(config)
        app.analyzer = analyzer
    except Exception as e:
        print(f"エンジンの初期化に失敗しました: {e}")
        app.analyzer = None

    # 4. 実行
    app.mainloop()

if __name__ == "__main__":
    main()