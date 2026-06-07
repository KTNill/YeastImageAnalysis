import pandas as pd
import os
import logging


class ConfigLoader:
    """
    解析設定を複数のCSV（共通、細胞、油脂、壊死）からロードし、管理するクラス。
    """
    CONFIG_SCHEMA = {
        # 共通設定 (config_common.csv)
        "透過光画像識別子": {"default": "_BF", "desc": "透過光（細胞用）画像のファイル名末尾（例: img01_BF.jpg）", "file": "config_common.csv"},
        "蛍光画像識別子": {"default": "_FL", "desc": "蛍光（油脂用）画像のファイル名末尾（例: img01_FL.jpg）", "file": "config_common.csv"},
        "PI蛍光画像識別子": {"default": "_PI", "desc": "PI蛍光（壊死用）画像のファイル名末尾（例: img01_PI.jpg）", "file": "config_common.csv"},
        "GPU使用": {"default": 1.0, "desc": "1でグラフィックボード（GPU）を使用して高速化、0で通常CPUを使用", "file": "config_common.csv"},
        "統合画像：細胞境界色": {"default": "255,255,255", "desc": "細胞枠の色。空欄でランダム。指定例: 255,255,255 または #FFFFFF", "file": "config_common.csv"},
        "統合画像：油脂色": {"default": "", "desc": "油脂の色。空欄でランダム。指定例: 0,255,255 または #00FFFF", "file": "config_common.csv"},
        "統合画像：壊死色": {"default": "", "desc": "壊死細胞の色。空欄でランダム. 指定例: 255,0,255 または #FF00FF", "file": "config_common.csv"},
        "統合画像：油脂なし細胞強調": {"default": 1.0, "desc": "1で油脂を持たない細胞を赤い太枠で強調表示、0で無効", "file": "config_common.csv"},
        "統合画像：生細胞強調": {"default": 1.0, "desc": "1で死んでいない（壊死していない）細胞を赤い太枠で強調表示、0で無効", "file": "config_common.csv"},

        # 細胞解析設定 (config_cell.csv)
        "細胞モデルパス": {"default": "models/custom_cpsam_v1", "desc": "細胞認識用Cellposeモデルのパス（空欄はデフォルトのcyto2を使用）", "file": "config_cell.csv"},
        "細胞径": {"default": 0.0, "desc": "細胞の直径。大きくすると小さなゴミを無視し、小さくすると小さな細胞まで拾います。", "file": "config_cell.csv"},
        "細胞フロー閾値": {"default": 0.4, "desc": "形の綺麗さ。上げると「綺麗な円形」だけを厳密に探し、下げると歪んだ形も拾います。", "file": "config_cell.csv"},
        "細胞確率閾値": {"default": 0.0, "desc": "検出感度。上げると「確実に細胞だ」と言える影だけを拾い、下げると背景に近い薄い影も細胞として扱います。", "file": "config_cell.csv"},
        "細胞最小サイズ": {"default": 150.0, "desc": "これより小さい面積のオブジェクトを無視します。", "file": "config_cell.csv"},
        "細胞マスク色": {"default": "", "desc": "細胞の描画色。空欄でランダム。指定例: 255,0,0 または #FF0000", "file": "config_cell.csv"},

        # 油脂解析設定 (config_lipid.csv)
        "油脂モデルパス": {"default": "", "desc": "油脂認識用Cellposeモデルのパス（空欄はデフォルトのcyto2を使用）", "file": "config_lipid.csv"},
        "油脂径": {"default": 0.0, "desc": "油脂の直径。大きくするとマスク範囲が広がり、小さくすると油脂の中心部のみを塗ります。", "file": "config_lipid.csv"},
        "油脂フロー閾値": {"default": 0.0, "desc": "形の制限。0にすると形を問わず光っている場所を全て塗り、上げると丸い粒だけを探します。", "file": "config_lipid.csv"},
        "油脂確率閾値": {"default": -4.0, "desc": "敏感さ。マイナスの値にするほど「ごく僅かな光」を油脂と見なし、プラスにするほど「強い光」のみを拾います。（目安：-2.0〜-4.0）", "file": "config_lipid.csv"},
        "油脂最小サイズ": {"default": 5.0, "desc": "これより小さい面積のゴミを無視します。", "file": "config_lipid.csv"},
        "油脂マスク色": {"default": "", "desc": "油脂の描画色。空欄でランダム。指定例: 0,255,255 または #00FFFF", "file": "config_lipid.csv"},
        "油脂ノイズカット閾値": {"default": 10.0, "desc": "解析前にこの値以下の明るさ（0～255）のピクセルを黒（0）にします。", "file": "config_lipid.csv"},
        "油脂平均輝度閾値": {"default": 10.0, "desc": "検出された油脂領域の平均の明るさがこの値（0～255）未満ならノイズとして除外します。", "file": "config_lipid.csv"},
        "油脂ガンマ補正": {"default": 1.1, "desc": "1.0より大きくするほど（例：1.2や1.3）、光の滲みを暗く潰してコアだけを残します。（1.0で無効）", "file": "config_lipid.csv"},
        "油脂輝度上限カット": {"default": 100.0, "desc": "これ以上の明るさ（0～255）のピクセルを指定値に頭打ちにし、薄い油脂の埋没を防ぎます。（255.0で無効。目安：80.0〜150.0）", "file": "config_lipid.csv"},
        "油脂ノイズぼかし幅": {"default": 2.0, "desc": "ノイズカット閾値の前後で滑らかに黒に消退させるグラデーションの幅（0〜255）。0.0で無効。", "file": "config_lipid.csv"},

        # 壊死解析設定 (config_necrosis.csv)
        "壊死モデルパス": {"default": "", "desc": "壊死細胞認識用Cellposeモデルのパス（空欄はデフォルトのcyto2を使用）", "file": "config_necrosis.csv"},
        "壊死径": {"default": 0.0, "desc": "壊死細胞の直径。大きくするとマスク範囲が広がり、小さくすると中心部のみを塗ります。", "file": "config_necrosis.csv"},
        "壊死フロー閾値": {"default": 0.0, "desc": "形の制限。0にすると形を問わず光っている場所を全て塗り、上げると丸い粒だけを探します。", "file": "config_necrosis.csv"},
        "壊死確率閾値": {"default": -2.0, "desc": "敏感さ。マイナスの値にするほど「ごく僅かな光」を壊死と見なし、プラスにするほど「強い光」のみを拾います。", "file": "config_necrosis.csv"},
        "壊死最小サイズ": {"default": 5.0, "desc": "これより小さい面積のゴミを無視します。", "file": "config_necrosis.csv"},
        "壊死マスク色": {"default": "", "desc": "壊死細胞の描画色。空欄でランダム。指定例: 255,0,255", "file": "config_necrosis.csv"},
        "壊死ノイズカット閾値": {"default": 5.0, "desc": "解析前にこの値（0～255）以下の明るさのピクセルを黒（0）にします。", "file": "config_necrosis.csv"},
        "壊死平均輝度閾値": {"default": 15.0, "desc": "検出された壊死領域の平均の明るさがこの値（0～255）未満ならノイズとして除外します。", "file": "config_necrosis.csv"},
        "壊死最小重複割合": {"default": 0.25, "desc": "細胞面積に対する単一PIマスクの重複割合（0.0〜1.0）。この値未満の被りなら壊死と判定しません。", "file": "config_necrosis.csv"},
        "壊死ガンマ補正": {"default": 1.0, "desc": "1.0より大きくするほど（例：1.5や2.0）、光の滲みを暗く潰してコアだけを残します。（1.0で無効）", "file": "config_necrosis.csv"},
        "壊死輝度上限カット": {"default": 255.0, "desc": "これ以上の明るさ（0～255）のピクセルを指定値に頭打ちにし、薄い壊死の埋没を防ぎます。（255.0で無効。目安：80.0〜150.0）", "file": "config_necrosis.csv"},
        "壊死ノイズぼかし幅": {"default": 0.0, "desc": "ノイズカット閾値の前後で滑らかに黒に消退させるグラデーションの幅（0〜255）。0.0で無効。", "file": "config_necrosis.csv"},
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
            if f_name not in file_items:
                file_items[f_name] = []
            file_items[f_name].append(jp_key)

        success_all = True
        new_settings = {}

        # 各ファイルごとに存在確認、無ければ生成、あれば読み込み
        for f_name, keys in file_items.items():
            f_path = os.path.join(self.config_dir, f_name)
            if not os.path.exists(f_path):
                self._create_default_csv(f_path, keys)

            try:
                df = pd.read_csv(f_path, encoding='utf-8-sig')
                required_columns = {"項目名", "設定値"}
                missing_columns = required_columns - set(df.columns)
                if missing_columns:
                    raise ValueError(f"設定CSV({f_name})に必要な列がありません: {', '.join(missing_columns)}")

                for jp_key in keys:
                    internal_key = self.KEY_MAP[jp_key]
                    row = df[df["項目名"] == jp_key]
                    val = row["設定値"].values[0] if not row.empty else self.CONFIG_SCHEMA[jp_key]["default"]

                    validated_val = self._validate_value(jp_key, val, self.CONFIG_SCHEMA[jp_key]["default"])
                    new_settings[internal_key] = validated_val

            except Exception as e:
                self.logger.error(f"Config load error for {f_name}: {e}")
                success_all = False
                # エラーが出たキーについてはデフォルト値を設定
                for jp_key in keys:
                    internal_key = self.KEY_MAP[jp_key]
                    new_settings[internal_key] = self.CONFIG_SCHEMA[jp_key]["default"]

        self.settings = new_settings
        return success_all

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

    def _create_default_csv(self, f_path, keys):
        data = []
        for jp_key in keys:
            info = self.CONFIG_SCHEMA[jp_key]
            data.append({
                "項目名": jp_key,
                "設定値": info["default"],
                "説明": info["desc"]
            })
        pd.DataFrame(data).to_csv(f_path, index=False, encoding='utf-8-sig')

    def get(self, key, default=None):
        return self.settings.get(key, default)
