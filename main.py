import logging
from utils.config_loader import ConfigLoader
from core.analyzer import YeastAnalyzer
from gui.app_window import App

def main():
    logging.basicConfig(level=logging.INFO)
    config = ConfigLoader("config/settings.csv")
    app = App()
    app.config_data = config
    try:
        app.analyzer = YeastAnalyzer(config)
    except Exception as e:
        print(f"初期化エラー: {e}")
    app.mainloop()

if __name__ == "__main__":
    main()