# YeastImageAnalysis
# Copyright (c) 2026 KT Nill
# This program is free software under the terms of the GNU GPL v3.

import pandas as pd
import os
import logging


class ConfigLoader:
    """
    解析設定を複数のCSV（共通、細胞、油脂、死細胞）からロード・保存し、管理するクラス。
    """
    CONFIG_SCHEMA = {
        # 共通設定 (config_common.csv)
        "透過光画像識別子": {"default": "_BF", "desc": "透過光（細胞用）画像のファイル名末尾（例: img01_BF.jpg）", "file": "config_common.csv"},
        "蛍光画像識別子": {"default": "_FL", "desc": "蛍光（油脂用）画像のファイル名末尾（例: img01_FL.jpg）", "file": "config_common.csv"},
        "PI蛍光画像識別子": {"default": "_PI", "desc": "PI蛍光（死細胞用）画像のファイル名末尾（例: img01_PI.jpg）", "file": "config_common.csv"},
        "GPU使用": {"default": 1.0, "desc": "1でグラフィックボード（GPU）を使用して高速化、0で通常CPUを使用", "file": "config_common.csv"},
        "統合画像：細胞境界色": {"default": "255,255,255", "desc": "細胞枠の色。指定例: 255,255,255 または #FFFFFF", "file": "config_common.csv"},
        "統合画像：油脂色": {"default": "", "desc": "油脂の色。空欄でランダム。指定例: 0,255,255", "file": "config_common.csv"},
        "統合画像：死細胞色": {"default": "", "desc": "死細胞の色。空欄でランダム. 指定例: 255,0,255", "file": "config_common.csv"},
        "統合画像：油脂なし細胞強調": {"default": 1.0, "desc": "1で油脂を持たない細胞を赤い太枠で強調表示、0で無効", "file": "config_common.csv"},
        "統合画像：生細胞強調": {"default": 1.0, "desc": "1で死細胞していない細胞を赤い太枠で強調表示、0で無効", "file": "config_common.csv"},

        # 細胞解析設定 (config_cell.csv)
        "細胞モデルパス": {"default": "models/custom_cpsam_v1", "desc": "細胞認識用Cellposeモデルのパス（空欄はデフォルトを使用）", "file": "config_cell.csv"},
        "細胞径": {"default": 0.0, "desc": "細胞の直径(px)。0で自動。推奨: 30.0〜60.0", "file": "config_cell.csv"},
        "細胞フロー閾値": {"default": 0.4, "desc": "形の綺麗さ。上げると「綺麗な円形」を厳密に探し、下げると歪んだ形も拾います。", "file": "config_cell.csv"},
        "細胞確率閾値": {"default": 0.0, "desc": "検出感度。上げると厳密に、下げると薄い影も細胞として扱います。", "file": "config_cell.csv"},
        "細胞最小サイズ": {"default": 150.0, "desc": "これより小さい面積のオブジェクトを無視します。", "file": "config_cell.csv"},
        "細胞マスク色": {"default": "", "desc": "細胞の描画色。空欄でランダム。", "file": "config_cell.csv"},

        # 油脂解析設定 (config_lipid.csv)
        "油脂モデルパス": {"default": "", "desc": "油脂認識用モデルパス（空欄はデフォルトを使用）", "file": "config_lipid.csv"},
        "油脂径": {"default": 0.0, "desc": "油脂の直径(px)。0で自動。", "file": "config_lipid.csv"},
        "油脂フロー閾値": {"default": 0.0, "desc": "形の制限。0で不問。上げると丸い粒だけを探します。", "file": "config_lipid.csv"},
        "油脂確率閾値": {"default": -4.0, "desc": "敏感さ。マイナスにするほど「ごく僅かな光」を油脂と見なします。", "file": "config_lipid.csv"},
        "油脂最小サイズ": {"default": 5.0, "desc": "これより小さい面積のゴミを無視します。", "file": "config_lipid.csv"},
        "油脂マスク色": {"default": "", "desc": "油脂の描画色。空欄でランダム。", "file": "config_lipid.csv"},
        "油脂ノイズカット閾値": {"default": 10.0, "desc": "この値以下の明るさ（0～255）を黒にします。", "file": "config_lipid.csv"},
        "油脂平均輝度閾値": {"default": 10.0, "desc": "油脂領域の平均の明るさがこの値未満なら除外します。", "file": "config_lipid.csv"},
        "油脂ガンマ補正": {"default": 1.1, "desc": "1.0より大きくするほど光の滲みを暗く潰します。", "file": "config_lipid.csv"},
        "油脂輝度上限カット": {"default": 100.0, "desc": "指定値（0～255）で明るさを頭打ちにし、薄い油脂の埋没を防ぎます。", "file": "config_lipid.csv"},
        "油脂ノイズぼかし幅": {"default": 2.0, "desc": "ノイズカットの境界を滑らかにする幅。0で無効。", "file": "config_lipid.csv"},

        # 死細胞解析設定 (config_necrosis.csv)
        "死細胞モデルパス": {"default": "", "desc": "死細胞用モデルパス（空欄はデフォルトを使用）", "file": "config_necrosis.csv"},
        "死細胞径": {"default": 0.0, "desc": "死細胞の直径(px)。0で自動。", "file": "config_necrosis.csv"},
        "死細胞フロー閾値": {"default": 0.0, "desc": "形の制限。0で不問。", "file": "config_necrosis.csv"},
        "死細胞確率閾値": {"default": -2.0, "desc": "敏感さ。マイナスにするほど死細胞と見なしやすくなります。", "file": "config_necrosis.csv"},
        "死細胞最小サイズ": {"default": 5.0, "desc": "これより小さい面積のゴミを無視します。", "file": "config_necrosis.csv"},
        "死細胞マスク色": {"default": "", "desc": "死細胞の描画色。空欄でランダム。", "file": "config_necrosis.csv"},
        "死細胞ノイズカット閾値": {"default": 5.0, "desc": "この値以下の明るさ（0～255）を黒にします。", "file": "config_necrosis.csv"},
        "死細胞平均輝度閾値": {"default": 15.0, "desc": "死細胞領域の平均の明るさがこの値未満なら除外します。", "file": "config_necrosis.csv"},
        "死細胞最小重複割合": {"default": 0.25, "desc": "細胞面積に対する重複割合（0〜1.0）。この値以上被れば死細胞と判定。", "file": "config_necrosis.csv"},
        "死細胞ガンマ補正": {"default": 1.0, "desc": "ガンマ補正値。1.0で無効。", "file": "config_necrosis.csv"},
        "死細胞輝度上限カット": {"default": 255.0, "desc": "輝度上限値。255.0で無効。", "file": "config_necrosis.csv"},
        "死細胞ノイズぼかし幅": {"default": 0.0, "desc": "ノイズカットの境界ぼかし。0で無効。", "file": "config_necrosis.csv"},
    }

    KEY_MAP = {
        "細胞モデルパス": "cell_model_path", "細胞径": "cell_diameter", "細胞フロー閾値": "cell_flow_threshold",
        "細胞確率閾値": "cell_cellprob_threshold", "細胞最小サイズ": "cell_min_size", "細胞マスク色": "cell_color",
        "油脂モデルパス": "lipid_model_path", "油脂径": "lipid_diameter", "油脂フロー閾値": "lipid_flow_threshold",
        "油脂確率閾値": "lipid_cellprob_threshold", "油脂最小サイズ": "lipid_min_size", "油脂マスク色": "lipid_color",
        "油脂ノイズカット閾値": "fl_noise_cutoff", "油脂平均輝度閾値": "fl_intensity_threshold",
        "油脂ガンマ補正": "fl_gamma", "油脂輝度上限カット": "fl_intensity_clip", "油脂ノイズぼかし幅": "fl_noise_fade_width",
        "死細胞モデルパス": "necrosis_model_path", "死細胞径": "necrosis_diameter", "死細胞フロー閾値": "necrosis_flow_threshold",
        "死細胞確率閾値": "necrosis_cellprob_threshold", "死細胞最小サイズ": "necrosis_min_size", "死細胞マスク色": "necrosis_color",
        "死細胞ノイズカット閾値": "pi_noise_cutoff", "死細胞平均輝度閾値": "pi_intensity_threshold",
        "死細胞最小重複割合": "necrosis_overlap_ratio", "死細胞ガンマ補正": "pi_gamma", "死細胞輝度上限カット": "pi_intensity_clip",
        "死細胞ノイズぼかし幅": "pi_noise_fade_width", "統合画像：細胞境界色": "combined_cell_color",
        "統合画像：油脂色": "combined_lipid_color", "統合画像：死細胞色": "combined_necrosis_color",
        "統合画像：油脂なし細胞強調": "highlight_lipid_negative_cells",
        "統合画像：生細胞強調": "highlight_necrosis_negative_cells",
        "透過光画像識別子": "bf_suffix", "蛍光画像識別子": "fl_suffix", "PI蛍光画像識別子": "pi_suffix", "GPU使用": "use_gpu"
    }

    def __init__(self, config_dir):
        self.logger = logging.getLogger(__name__)
        self.config_dir = config_dir
        self.settings = {}
        self.load_config()

    def load_config(self):
        """設定CSVファイルを読み込み、最新の設定値をメモリにロードする"""
        os.makedirs(self.config_dir, exist_ok=True)

        # ファイル名ごとに存在するべき項目を整理する
        file_items = {}
        for jp_key, info in self.CONFIG_SCHEMA.items():
            f_name = info["file"]
            if f_name not in file_items: file_items[f_name] = []
            file_items[f_name].append(jp_key)

        new_settings = {}

        # 各ファイルごとに存在確認、無ければ生成、あれば読み込み
        for f_name, keys in file_items.items():
            f_path = os.path.join(self.config_dir, f_name)
            if not os.path.exists(f_path): self._create_default_csv(f_path, keys)
            try:
                # dtype=str を指定して自動型推論を無効化
                df = pd.read_csv(f_path, encoding='utf-8-sig', dtype=str)
                for jp_key in keys:
                    internal_key = self.KEY_MAP[jp_key]
                    row = df[df["項目名"] == jp_key]
                    val = row["設定値"].values[0] if not row.empty else self.CONFIG_SCHEMA[jp_key]["default"]
                    new_settings[internal_key] = self._validate_value(jp_key, val, self.CONFIG_SCHEMA[jp_key]["default"])
            except Exception as e:
                self.logger.error(f"Config load error: {e}")
                for jp_key in keys: new_settings[self.KEY_MAP[jp_key]] = self.CONFIG_SCHEMA[jp_key]["default"]
        self.settings = new_settings
        return True

    def save_config(self, updates_dict):
        """GUIからの更新をCSVとメモリに反映"""
        rev_map = {v: k for k, v in self.KEY_MAP.items()}
        files_to_update = set()
        for int_key in updates_dict.keys():
            jp_key = rev_map.get(int_key)
            if jp_key in self.CONFIG_SCHEMA:
                files_to_update.add(self.CONFIG_SCHEMA[jp_key]["file"])

        for f_name in files_to_update:
            f_path = os.path.join(self.config_dir, f_name)
            try:
                # dtype=str を指定して自動型推論を無効化
                df = pd.read_csv(f_path, encoding='utf-8-sig', dtype=str)
                for int_key, new_val in updates_dict.items():
                    jp_key = rev_map.get(int_key)
                    if jp_key and self.CONFIG_SCHEMA[jp_key]["file"] == f_name:
                        # メモリ上の設定を更新
                        self.settings[int_key] = self._validate_value(jp_key, new_val, self.CONFIG_SCHEMA[jp_key]["default"])
                        # DataFrameを更新 (文字列として代入されるため型エラーが起きない)
                        df.loc[df["項目名"] == jp_key, "設定値"] = str(new_val)
                df.to_csv(f_path, index=False, encoding='utf-8-sig')
            except Exception as e:
                self.logger.error(f"Config save error: {e}")
                return False
        return True

    def _validate_value(self, key, value, default):
        if pd.isna(value) or str(value).strip() == "": return default
        if isinstance(default, str): return str(value).strip()
        try:
            return float(value)
        except:
            return default

    def _create_default_csv(self, f_path, keys):
        data = [{"項目名": k,
                 "設定値": self.CONFIG_SCHEMA[k]["default"],
                 "説明": self.CONFIG_SCHEMA[k]["desc"]
                 } for k in keys]
        pd.DataFrame(data).to_csv(f_path, index=False, encoding='utf-8-sig')

    def get(self, key, default=None):
        return self.settings.get(key, default)
