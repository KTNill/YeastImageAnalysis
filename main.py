# Entry point for Yeast Analysis App
import sys
import logging
from utils.config_loader import ConfigLoader
from core.analyzer import YeastAnalyzer
from gui.app_window import App

def main():
    # 1. ロギングの設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("YeastApp")

    try:
        # 2. 設定の読み込み
        logger.info("設定ファイルを読み込んでいます...")
        config = ConfigLoader("config/settings.csv")

        # 3. 解析エンジンの初期化 (GPU設定などを反映)
        logger.info("解析エンジン(Cellpose)を初期化しています...")
        analyzer = YeastAnalyzer(
            use_gpu=bool(config.get("use_gpu"))
        )

        # 4. GUIの起動
        logger.info("GUIを起動します...")
        app = App()

        # GUIに設定と解析エンジンを紐付け
        app.config_data = config
        app.analyzer = analyzer

        # GUIの実行
        app.mainloop()

    except Exception as e:
        logger.error(f"アプリケーションの起動中にエラーが発生しました: {e}")
        # GUIが起動する前のエラーはコンソールまたはダイアログで通知
        import tkinter.messagebox as mb
        mb.showerror("起動エラー", f"アプリを起動できませんでした。\n理由: {str(e)}")
        sys.exit(1)
if __name__ == "__main__":
    main()
