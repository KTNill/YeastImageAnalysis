import pandas as pd
import os
import logging
from pathlib import Path

# プロジェクトのルートディレクトリを取得 (appフォルダの1つ上)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

class ConfigLoader:
    """
    解析設定をCSVからロードし、管理するクラス。
    """
    CONFIG_SCHEMA = {
        "細胞モデルパス": {"default": "", "desc": "細胞認識用モデル"},
        "細胞径": {"default": 30.0, "desc": "細胞の想定直径"},
        "細胞フロー閾値": {"default": 0.4, "desc": "細胞のフロー閾値"},
        "細胞確率閾値": {"default": 0.0, "desc": "細胞の確率閾値"},
        "細胞最小サイズ": {"default": 150.0, "desc": "最小細胞ピクセル数"},
        "細胞マスク色": {"default": "", "desc": "細胞の描画色"},

        "油脂モデルパス": {"default": "", "desc": "油脂認識用モデル"},
        "油脂径": {"default": 10.0, "desc": "油脂の想定直径"},
        "油脂フロー閾値": {"default": 0.5, "desc": "油脂のフロー閾値"},
        "油脂確率閾値": {"default": 1.0, "desc": "油脂の確率閾値"},
        "油脂最小サイズ": {"default": 20.0, "desc": "最小油脂ピクセル数"},
        "油脂マスク色": {"default": "", "desc": "油脂の描画色"},

        "統合画像：細胞境界色": {"default": "255,255,255", "desc": "細胞枠の色"},
        "統合画像：油脂色": {"default": "", "desc": "油脂の色"},

        "透過光画像識別子": {"default": "_BF", "desc": "透過光画像識別子"},
        "蛍光画像識別子": {"default": "_FL", "desc": "蛍光画像識別子"},
        "GPU使用": {"default": 1.0, "desc": "GPU利用"}
    }

    KEY_MAP = {
        "細胞モデルパス": "cell_model_path",
        "細胞径": "cell_diameter",
        "細胞フロー閾値": "cell_flow_threshold",
        "細胞確率閾値": "cell_cellprob_threshold",
        "細胞最小サイズ": "cell_min_size",
        "細胞マスク色": "cell_color",
        "油脂モデルパス": "lipid_model_path",
        "油脂径": "lipid_diameter",
        "油脂フロー閾値": "lipid_flow_threshold",
        "油脂確率閾値": "lipid_cellprob_threshold",
        "油脂最小サイズ": "lipid_min_size",
        "油脂マスク色": "lipid_color",
        "統合画像：細胞境界色": "combined_cell_color",
        "統合画像：油脂色": "combined_lipid_color",
        "透過光画像識別子": "bf_suffix",
        "蛍光画像識別子": "fl_suffix",
        "GPU使用": "use_gpu"
    }

    def __init__(self, config_path):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.settings = {}
        self.load_config()

    def load_config(self):
        """CSVファイルを読み込み、最新の設定値をメモリにロードする"""
        if not os.path.exists(self.config_path):
            self._create_default_csv()

        try:
            df = pd.read_csv(self.config_path, encoding='utf-8-sig')
            new_settings = {}
            for jp_key, internal_key in self.KEY_MAP.items():
                row = df[df["項目名"] == jp_key]
                val = row["設定値"].values[0] if not row.empty else self.CONFIG_SCHEMA[jp_key]["default"]

                validated_val = self._validate_value(jp_key, val, self.CONFIG_SCHEMA[jp_key]["default"])

                if internal_key.endswith("_path") and validated_val:
                    new_settings[internal_key] = os.path.join(BASE_DIR, validated_val)
                else:
                    new_settings[internal_key] = validated_val

            self.settings = new_settings
        except Exception as e:
            self.logger.error(f"Config load error: {e}")
            if not self.settings:
                self._apply_all_defaults()

    def _validate_value(self, key, value, default):
        if pd.isna(value) or str(value).strip() == "":
            return default
        if isinstance(default, str):
            return str(value).strip()
        try:
            return float(value)
        except:
            return default

    def _apply_all_defaults(self):
        for jp_key, internal_key in self.KEY_MAP.items():
            self.settings[internal_key] = self.CONFIG_SCHEMA[jp_key]["default"]

    def _create_default_csv(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = [{"項目名": k, "設定値": v["default"], "説明": v["desc"]} for k, v in self.CONFIG_SCHEMA.items()]
        pd.DataFrame(data).to_csv(self.config_path, index=False, encoding='utf-8-sig')

    def get(self, key):
        return self.settings.get(key)