import pandas as pd
import os
import logging


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
        "油脂ノイズカット閾値": {"default": 10.0, "desc": "解析前にこの値以下の明るさのピクセルを黒（0）にします。"},
        "油脂平均輝度閾値": {"default": 20.0, "desc": "検出された油脂領域の平均の明るさがこの値未満ならノイズとして除外します。"},
        "油脂ガンマ補正": {"default": 1.0, "desc": "1.0より大きくするほど（例：1.5や2.0）、光の滲みを暗く潰してコアだけを残します。（1.0で無効）"},
        "油脂輝度上限カット": {"default": 255.0, "desc": "これ以上の明るさのピクセルを指定値に頭打ちにし、薄い油脂の埋没を防ぎます。（255.0で無効）"},
        "油脂ノイズぼかし幅": {"default": 0.0, "desc": "ノイズカット閾値の前後で滑らかに黒に消退させるグラデーションの幅（0〜255）。0.0で無効。"},

        "壊死モデルパス": {"default": "", "desc": "壊死細胞認識用Cellposeモデルのパス（空欄はデフォルトのcyto2を使用）"},
        "壊死径": {"default": 10.0, "desc": "壊死細胞の直径。"},
        "壊死フロー閾値": {"default": 0.5, "desc": "壊死細胞の形の制限。"},
        "壊死確率閾値": {"default": 1.0, "desc": "壊死細胞の敏感さ。"},
        "壊死最小サイズ": {"default": 20.0, "desc": "これより小さい面積のゴミを無視します。"},
        "壊死マスク色": {"default": "", "desc": "空欄でランダム。指定例: 255,0,255"},
        "壊死ノイズカット閾値": {"default": 10.0, "desc": "解析前にこの値以下の明るさのピクセルを黒（0）にします。"},
        "壊死平均輝度閾値": {"default": 20.0, "desc": "検出された壊死領域の平均の明るさがこの値未満ならノイズとして除外します。"},
        "壊死最小重複割合": {"default": 0.0, "desc": "細胞面積に対する単一PIマスク of 重複割合（0.0〜1.0）。この値未満の被りなら壊死と判定しません。"},
        "壊死ガンマ補正": {"default": 1.0, "desc": "1.0より大きくするほど（例：1.5や2.0）、光の滲みを暗く潰してコアだけを残します。（1.0で無効）"},
        "壊死輝度上限カット": {"default": 255.0, "desc": "これ以上の明るさのピクセルを指定値に頭打ちにし、薄い壊死の埋没を防ぎます。（255.0で無効）"},
        "壊死ノイズぼかし幅": {"default": 0.0, "desc": "ノイズカット閾値の前後で滑らかに黒に消退させるグラデーションの幅（0〜255）。0.0で無効。"},

        "統合画像：細胞境界色": {"default": "255,255,255", "desc": "細胞枠の色"},
        "統合画像：油脂色": {"default": "", "desc": "油脂の色"},
        "統合画像：壊死色": {"default": "", "desc": "空欄でランダム"},
        "統合画像：油脂なし細胞強調": {"default": 1.0, "desc": "1で油脂を持たない細胞を強調表示、0で無効"},
        "統合画像：生細胞強調": {"default": 1.0, "desc": "1で死んでいない（壊死していない）細胞を強調表示、0で無効"},

        "透過光画像識別子": {"default": "_BF", "desc": "透過光画像識別子"},
        "蛍光画像識別子": {"default": "_FL", "desc": "蛍光画像識別子"},
        "PI蛍光画像識別子": {"default": "_PI", "desc": "PI蛍光（壊死用）画像のファイル名末尾"},
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
        "油脂ノイズカット閾値": "fl_noise_cutoff",
        "油脂平均輝度閾値": "fl_intensity_threshold",
        "油脂ガンマ補正": "fl_gamma",
        "油脂輝度上限カット": "fl_intensity_clip",
        "油脂ノイズぼかし幅": "fl_noise_fade_width",
        "壊死モデルパス": "necrosis_model_path",
        "壊死径": "necrosis_diameter",
        "壊死フロー閾値": "necrosis_flow_threshold",
        "壊死確率閾値": "necrosis_cellprob_threshold",
        "壊死最小サイズ": "necrosis_min_size",
        "壊死マスク色": "necrosis_color",
        "壊死ノイズカット閾値": "pi_noise_cutoff",
        "壊死平均輝度閾値": "pi_intensity_threshold",
        "壊死最小重複割合": "necrosis_overlap_ratio",
        "壊死ガンマ補正": "pi_gamma",
        "壊死輝度上限カット": "pi_intensity_clip",
        "壊死ノイズぼかし幅": "pi_noise_fade_width",
        "統合画像：細胞境界色": "combined_cell_color",
        "統合画像：油脂色": "combined_lipid_color",
        "統合画像：壊死色": "combined_necrosis_color",
        "統合画像：油脂なし細胞強調": "highlight_lipid_negative_cells",
        "統合画像：生細胞強調": "highlight_necrosis_negative_cells",
        "透過光画像識別子": "bf_suffix",
        "蛍光画像識別子": "fl_suffix",
        "PI蛍光画像識別子": "pi_suffix",
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
            required_columns = {"項目名", "設定値"}
            missing_columns = required_columns - set(df.columns)
            if missing_columns:
                raise ValueError(f"設定CSVに必要な列がありません: {', '.join(missing_columns)}")

            new_settings = {}
            for jp_key, internal_key in self.KEY_MAP.items():
                row = df[df["項目名"] == jp_key]
                val = row["設定値"].values[0] if not row.empty else self.CONFIG_SCHEMA[jp_key]["default"]

                validated_val = self._validate_value(jp_key, val, self.CONFIG_SCHEMA[jp_key]["default"])

                new_settings[internal_key] = validated_val

            self.settings = new_settings

            return True
        except Exception as e:
            self.logger.error(f"Config load error: {e}")
            if not self.settings:
                self._apply_all_defaults()

            return False

    def _validate_value(self, key, value, default):
        if pd.isna(value) or str(value).strip() == "":
            return default
        if isinstance(default, str):
            return str(value).strip()
        try:
            return float(value)
        except Exception as e:
            self.logger.error(f"Config value cast to float error: {e}")
            return default

    def _apply_all_defaults(self):
        for jp_key, internal_key in self.KEY_MAP.items():
            self.settings[internal_key] = self.CONFIG_SCHEMA[jp_key]["default"]

    def _create_default_csv(self):
        config_dir = os.path.dirname(self.config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)

        data = [{"項目名": k, "設定値": v["default"], "説明": v["desc"]} for k, v in self.CONFIG_SCHEMA.items()]
        pd.DataFrame(data).to_csv(self.config_path, index=False, encoding='utf-8-sig')

    def get(self, key, default=None):
        return self.settings.get(key, default)
