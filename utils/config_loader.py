# CSV/Settings loader
import pandas as pd
import os
import logging

from pandas import DataFrame


class ConfigLoader:
    """
    config/settings.csv から設定を読み込み、バリデーションを行うクラス。
    日本語ヘッダーに対応し、異常値にはデフォルト値を適用します。
    """

    # デフォルト値の定義
    DEFAULTS = {
        "細胞径": 30.0,
        "油脂輝度閾値": 0.0,  # 0の場合は自動(大津の二値化)
        "真円度閾値": 0.5,
        "GPU使用": 1,        # 1: 使用する, 0: 使用しない
    }

    # CSVの日本語項目名と内部変数名のマッピング
    KEY_MAP = {
        "細胞径": "cell_diameter",
        "油脂輝度閾値": "lipid_threshold",
        "真円度閾値": "min_circularity",
        "GPU使用": "use_gpu"
    }

    def __init__(self, config_path="config/settings.csv"):
        self.config_path = config_path
        self.settings = {}
        self.logger = logging.getLogger(__name__)
        self.load_config()

    def load_config(self):
        """CSVファイルを読み込み、設定値を辞書に格納します。"""
        # ファイルが存在しない場合はデフォルトで作成
        if not os.path.exists(self.config_path):
            self._create_default_csv()

        try:
            # Excelで編集されることを想定し、utf-8-sig (BOM付き) で読み込み
            df = pd.read_csv(self.config_path, encoding='utf-8-sig')

            # 1列目を「項目名」、2列目を「値」として処理
            # 列名が日本語でも対応できるよう、位置（iloc）で取得
            config_dict = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))

            for jp_key, default_val in self.DEFAULTS.items():
                raw_val = config_dict.get(jp_key)

                # バリデーション実行
                self.settings[self.KEY_MAP[jp_key]] = self._validate_value(
                    jp_key, raw_val, default_val
                )

            self.logger.info("設定ファイルを読み込みました。")

        except Exception as e:
            self.logger.error(f"設定ファイルの読み込み中にエラー: {e}")
            self.logger.info("安全のためデフォルト値を使用します。")
            self._apply_all_defaults()

    def _validate_value(self, key, value, default):
        """値が数値か、空でないかをチェックし、不適切な場合はデフォルト値を返します。"""
        if pd.isna(value) or value == "":
            return default

        try:
            return float(value)
        except (ValueError, TypeError):
            self.logger.warning(
                f"設定エラー: '{key}' の値 '{value}' が正しくありません。"
                f"デフォルト値 {default} を使用します。"
            )
            return default

    def _apply_all_defaults(self):
        """全ての値をデフォルト値に設定します。"""
        for jp_key, internal_key in self.KEY_MAP.items():
            self.settings[internal_key] = self.DEFAULTS[jp_key]

    def _create_default_csv(self):
        """デフォルトの設定ファイルを作成します。"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        df = pd.DataFrame([
            {"項目名": k, "設定値": v, "説明": "※この列は編集不要です"}
            for k, v in self.DEFAULTS.items()
        ])
        # Excelでの編集を考慮し BOM付きUTF-8 で保存
        df.to_csv(self.config_path, index=False, encoding='utf-8-sig')
        self.logger.info(f"新規設定ファイルを作成しました: {self.config_path}")

    def get(self, key):
        """内部変数名を指定して設定値を取得します。"""
        return self.settings.get(key)

    @property
    def all_settings(self):
        """全設定を辞書形式で取得します。"""
        return self.settings

# 利用例
if __name__ == "__main__":
    loader = ConfigLoader()
    print(f"読み込まれた設定: {loader.all_settings}")
    print(f"細胞径: {loader.get('cell_diameter')}")
