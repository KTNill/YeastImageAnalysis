import torch
import numpy as np
import os
import cv2
import logging
from skimage.segmentation import find_boundaries


class YeastAnalyzer:
    """
    透過光(BF)、蛍光(FL)、PI蛍光(PI)画像を解析し、細胞数および油脂・壊死細胞の分布を定量化する。
    """

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.cfg = config

        use_gpu = bool(config.get("use_gpu"))
        self.device_available = False

        if use_gpu and torch.cuda.is_available():
            self.device = "cuda"
            self.device_available = True
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = False
            torch.set_float32_matmul_precision("highest")
        elif use_gpu and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
            self.device_available = True
        else:
            self.device = "cpu"

        self.logger.info(f"解析デバイス: {self.device}")

        # CellposeModelの初期化
        self.cell_model = self._load_model(config.get("cell_model_path"), "cyto2", "細胞用")
        self.lipid_model = self._load_model(config.get("lipid_model_path"), "cyto2", "油脂用")
        self.necrosis_model = self._load_model(config.get("necrosis_model_path"), "cyto2", "壊死用")

    def _load_model(self, model_path, fallback_model, model_name):
        try:
            from cellpose.models import CellposeModel

            if model_path and os.path.exists(model_path):
                return CellposeModel(gpu=self.device_available, pretrained_model=model_path)
            return CellposeModel(gpu=self.device_available, model_type=fallback_model)
        except Exception as e:
            self.logger.error(f"{model_name}モデルの初期化失敗: {e}")
            raise

    def _apply_cutoff(self, image, threshold):
        """案1: 指定輝度以下のピクセルを0（黒）にする前処理 (0〜255スケールで指定)"""
        th_val = float(threshold)
        if th_val <= 0:
            return image

        # 画像が16bit(uint16)の場合は、0〜255の閾値を0〜65535スケールに自動変換する
        if image.dtype == np.uint16:
            th_val = th_val * (65535.0 / 255.0)
            max_val = 65535
        else:
            max_val = 255

        _, img_clean = cv2.threshold(image, th_val, max_val, cv2.THRESH_TOZERO)
        return img_clean

    def _filter_masks_by_intensity(self, masks, original_image, intensity_threshold):
        """案2: マスク内の平均輝度が閾値未満のマスクを除外する後処理 (0〜255スケールで指定)"""
        th_val = float(intensity_threshold)
        if th_val <= 0:
            return masks

        # 画像が16bit(uint16)の場合は、0〜255の閾値を0〜65535スケールに自動変換する
        if original_image.dtype == np.uint16:
            th_val = th_val * (65535.0 / 255.0)

        new_masks = np.zeros_like(masks)
        max_id = int(np.max(masks))
        current_new_id = 1

        for i in range(1, max_id + 1):
            mask_area = (masks == i)
            if not np.any(mask_area):
                continue

            # マスク領域の元画像における平均輝度を算出
            mean_intensity = np.mean(original_image[mask_area])

            if mean_intensity >= th_val:
                new_masks[mask_area] = current_new_id
                current_new_id += 1

        return new_masks

    def analyze(self, bf_image, fl_image=None, pi_image=None, run_cell=True, run_lipid=True, run_necrosis=False, progress_callback=None):
        results = {}
        visuals = {}

        # 1. 細胞解析（透過光）
        cell_masks = None
        total_cell_px = 0
        if run_cell and bf_image is not None:
            if progress_callback: progress_callback(0.1)
            cell_masks, _, _ = self.cell_model.eval(
                bf_image, diameter=self.cfg.get("cell_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("cell_flow_threshold"),
                cellprob_threshold=self.cfg.get("cell_cellprob_threshold"),
                min_size=self.cfg.get("cell_min_size")
            )
            total_cell_px = int(np.sum(cell_masks > 0))
            results["cell_count"] = int(np.max(cell_masks))
            results["total_cell_px"] = total_cell_px
            visuals["cell"] = self._draw_masks(bf_image, cell_masks, True, self.cfg.get("cell_color"))

        # 2. 油脂解析（蛍光）
        lipid_masks = None
        total_lipid_px = 0
        if run_lipid and fl_image is not None:
            if progress_callback: progress_callback(0.4)

            fl_clean = self._apply_cutoff(fl_image, self.cfg.get("fl_noise_cutoff", 10.0))

            lipid_masks, _, _ = self.lipid_model.eval(
                fl_clean, diameter=self.cfg.get("lipid_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("lipid_flow_threshold"),
                cellprob_threshold=self.cfg.get("lipid_cellprob_threshold"),
                min_size=self.cfg.get("lipid_min_size")
            )

            lipid_masks = self._filter_masks_by_intensity(
                lipid_masks, fl_image, self.cfg.get("fl_intensity_threshold", 20.0)
            )

            total_lipid_px = int(np.sum(lipid_masks > 0))
            results["lipid_count"] = int(np.max(lipid_masks))
            results["total_lipid_px"] = total_lipid_px
            visuals["lipid"] = self._draw_masks(fl_image, lipid_masks, False, self.cfg.get("lipid_color"))

        # 3. 統合解析（油脂）
        if run_cell and run_lipid and cell_masks is not None and lipid_masks is not None:
            if cell_masks.shape != lipid_masks.shape:
                raise ValueError(
                    f"細胞マスクと油脂マスクのサイズが一致しません: "
                    f"cell={cell_masks.shape}, lipid={lipid_masks.shape}"
                )

            integrated_masks = np.where(cell_masks > 0, lipid_masks, 0)
            integrated_px = int(np.sum(integrated_masks > 0))
            extracellular_px = total_lipid_px - integrated_px
            lipid_cell_ids = np.unique(cell_masks[np.logical_and(cell_masks > 0, lipid_masks > 0)])
            lipid_positive_cell_count = int(len(lipid_cell_ids))
            cell_count = int(results.get("cell_count", 0))

            results["lipid_cell_ratio"] = integrated_px / total_cell_px if total_cell_px > 0 else 0.0
            results["total_production_ratio"] = total_lipid_px / total_cell_px if total_cell_px > 0 else 0.0
            results["intracellular_lipid_percent"] = integrated_px / total_lipid_px if total_lipid_px > 0 else 0.0
            results["extracellular_lipid_percent"] = extracellular_px / total_lipid_px if total_lipid_px > 0 else 0.0
            results["lipid_positive_cell_count"] = lipid_positive_cell_count
            results["lipid_positive_cell_ratio"] = lipid_positive_cell_count / cell_count if cell_count > 0 else 0.0
            results["integrated_lipid_px"] = integrated_px
            results["extracellular_lipid_px"] = extracellular_px

            visuals["combined"] = self._draw_combined(
                bf_image, cell_masks, lipid_masks,
                self.cfg.get("combined_cell_color"), self.cfg.get("combined_lipid_color"),
                highlight_flag=bool(self.cfg.get("highlight_lipid_negative_cells", 1.0))
            )

        # 4. 壊死解析（PI蛍光）
        necrosis_masks = None
        total_necrosis_px = 0
        if run_necrosis and pi_image is not None:
            if progress_callback: progress_callback(0.7)

            pi_clean = self._apply_cutoff(pi_image, self.cfg.get("pi_noise_cutoff", 10.0))

            necrosis_masks, _, _ = self.necrosis_model.eval(
                pi_clean, diameter=self.cfg.get("necrosis_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("necrosis_flow_threshold"),
                cellprob_threshold=self.cfg.get("necrosis_cellprob_threshold"),
                min_size=self.cfg.get("necrosis_min_size")
            )

            necrosis_masks = self._filter_masks_by_intensity(
                necrosis_masks, pi_image, self.cfg.get("pi_intensity_threshold", 20.0)
            )

            total_necrosis_px = int(np.sum(necrosis_masks > 0))
            results["necrosis_count"] = int(np.max(necrosis_masks))
            results["total_necrosis_px"] = total_necrosis_px
            visuals["necrosis"] = self._draw_masks(pi_image, necrosis_masks, False, self.cfg.get("necrosis_color"))

        # 5. 統合解析（壊死）
        if run_cell and run_necrosis and cell_masks is not None and necrosis_masks is not None:
            if cell_masks.shape != necrosis_masks.shape:
                raise ValueError(
                    f"細胞マスクと壊死マスクのサイズが一致しません: "
                    f"cell={cell_masks.shape}, necrosis={necrosis_masks.shape}"
                )

            cell_count = int(results.get("cell_count", 0))

            # 【新規】重複割合の閾値を取得
            necrosis_overlap_ratio = float(self.cfg.get("necrosis_overlap_ratio", 0.0))

            overlap_mask = np.logical_and(cell_masks > 0, necrosis_masks > 0)
            overlap_cells = cell_masks[overlap_mask]
            overlap_necrosis = necrosis_masks[overlap_mask]

            valid_necrosis_cell_ids = []

            if len(overlap_cells) > 0:
                # 各細胞の総ピクセル数を計算
                cell_areas = np.bincount(cell_masks.ravel())

                # 重なっている（細胞ID, PIマスクID）のペアごとにピクセル数を集計する
                max_necrosis_id = int(np.max(necrosis_masks))
                offset = int(max_necrosis_id + 1)

                # 2つのIDを1つに合成してカウント（オーバーフロー防止のためint64を使用）
                combined_ids = overlap_cells.astype(np.int64) * offset + overlap_necrosis.astype(np.int64)
                unique_comb, counts = np.unique(combined_ids, return_counts=True)

                # 合成したIDを元の細胞IDに戻す
                c_ids = (unique_comb // offset).astype(int)

                # 「それぞれのPIマスクと細胞の重複面積」 ÷ 「細胞自体の面積」
                ratios = counts / cell_areas[c_ids]

                # 指定した閾値以上の重複を持つ細胞IDだけを抽出
                valid_mask = ratios >= necrosis_overlap_ratio
                valid_necrosis_cell_ids = np.unique(c_ids[valid_mask]).tolist()

            necrosis_positive_cell_count = len(valid_necrosis_cell_ids)

            results["necrosis_positive_cell_count"] = necrosis_positive_cell_count
            results["necrosis_positive_cell_ratio"] = necrosis_positive_cell_count / cell_count if cell_count > 0 else 0.0

            visuals["combined_necrosis"] = self._draw_combined(
                bf_image, cell_masks, necrosis_masks,
                self.cfg.get("combined_cell_color"), self.cfg.get("combined_necrosis_color"),
                highlight_flag=bool(self.cfg.get("highlight_necrosis_negative_cells", 1.0)),
                positive_cell_ids=valid_necrosis_cell_ids  # 条件を満たした壊死細胞のみを対象にする
            )

        return results, visuals

    @staticmethod
    def _parse_color(color_str):
        if not color_str:
            return None

        try:
            c = str(color_str).strip()
            if "," in c:
                values = [int(x.strip()) for x in c.split(",")]
                if len(values) == 3 and all(0 <= value <= 255 for value in values):
                    return values
                return None

            if c.startswith("#") and len(c) == 7:
                return [int(c[5:7], 16), int(c[3:5], 16), int(c[1:3], 16)]
        except Exception:
            return None

        return None

    @staticmethod
    def _color_for_id(mask_id, salt=0):
        rng = np.random.default_rng((int(mask_id) * 1009) + salt)
        return rng.integers(100, 255, size=3).tolist()

    @staticmethod
    def _prepare_canvas(img):
        if len(img.shape) == 2:
            canvas = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            canvas = img.copy()
        if canvas.dtype != np.uint8:
            canvas = cv2.normalize(canvas, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        return canvas

    def _draw_masks(self, img, masks, highlight_boundaries, color_str):
        canvas = self._prepare_canvas(img)
        overlay = canvas.copy()
        max_id = int(np.max(masks))
        base_color = self._parse_color(color_str)
        if max_id > 0:
            for i in range(1, max_id + 1):
                color = base_color if base_color is not None else self._color_for_id(i)
                overlay[masks == i] = color
        blended = cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0)
        if highlight_boundaries and max_id > 0:
            blended[find_boundaries(masks, mode='inner')] = [255, 255, 255]
        return blended

    def _draw_combined(self, img, cell_masks, sub_masks, cell_color_str, sub_color_str, highlight_flag=False, positive_cell_ids=None):
        canvas = self._prepare_canvas(img)
        max_cell_id = int(np.max(cell_masks))
        cell_color = self._parse_color(cell_color_str)
        if max_cell_id > 0:
            bounds = find_boundaries(cell_masks, mode='inner')
            if cell_color is not None:
                canvas[bounds] = cell_color
            else:
                for i in range(1, max_cell_id + 1):
                    canvas[np.logical_and(bounds, cell_masks == i)] = self._color_for_id(i, salt=10_000)

        overlay = canvas.copy()
        max_sub_id = int(np.max(sub_masks))
        sub_color = self._parse_color(sub_color_str)
        if max_sub_id > 0:
            for i in range(1, max_sub_id + 1):
                color = sub_color if sub_color is not None else self._color_for_id(i, salt=20_000)
                overlay[sub_masks == i] = color

        combined = cv2.addWeighted(overlay, 0.5, canvas, 0.5, 0)

        if highlight_flag and max_cell_id > 0:
            # 外部から指定された陽性細胞リストがあれば使い、無ければ全てのかぶっている細胞を取得する
            if positive_cell_ids is None:
                positive_cell_ids_set = set(
                    np.unique(cell_masks[np.logical_and(cell_masks > 0, sub_masks > 0)]).astype(int).tolist()
                )
            else:
                positive_cell_ids_set = set(positive_cell_ids)

            for cell_id in range(1, max_cell_id + 1):
                # 陽性細胞（油脂保有 または 壊死判定された細胞）は赤枠強調をスキップ
                if cell_id in positive_cell_ids_set:
                    continue

                single_cell_mask = (cell_masks == cell_id).astype(np.uint8)
                contours, _ = cv2.findContours(
                    single_cell_mask,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE
                )
                cv2.drawContours(
                    combined,
                    contours,
                    -1,
                    [0, 0, 255],
                    thickness=3
                )

        return combined
