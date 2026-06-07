import torch
import numpy as np
import os
import cv2
import logging
from enum import Enum, auto
from skimage.segmentation import find_boundaries


class LogCategory(Enum):
    """解析プロセスにおけるイベントの論理分類"""
    NORMAL = auto()
    EVENT_START = auto()  # 解析開始
    EVENT_END = auto()  # 解析終了（サマリー・完了）
    WARNING = auto()
    ERROR = auto()


class YeastAnalyzer:
    """
    透過光(BF)、蛍光(FL)、PI蛍光(PI)画像を解析し、細胞数および油脂・壊死細胞の分布を定量化する。
    """

    def __init__(self, config, log_callback=None):
        self.logger = logging.getLogger(__name__)
        self.cfg = config
        self.log_callback = log_callback  # (msg, category, metadata={})

        use_gpu = bool(config.get("use_gpu"))
        self.device_available = False

        if use_gpu and torch.cuda.is_available():
            self.device = "cuda"
            self.device_available = True
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.set_float32_matmul_precision("highest")
        elif use_gpu and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
            self.device_available = True
        else:
            self.device = "cpu"

        self._log(f"解析デバイス: {self.device}")

        self.cell_model = None
        self.lipid_model = None
        self.necrosis_model = None

    def _log(self, msg, category=LogCategory.NORMAL, metadata=None):
        self.logger.info(msg)
        if self.log_callback:
            self.log_callback(msg, category, metadata)

    def get_cell_model(self):
        if self.cell_model is None:
            self.cell_model = self._load_model(self.cfg.get("cell_model_path"), "cpsam", "細胞用")
        return self.cell_model

    def get_lipid_model(self):
        if self.lipid_model is None:
            self.lipid_model = self._load_model(self.cfg.get("lipid_model_path"), "cpsam", "油脂用")
        return self.lipid_model

    def get_necrosis_model(self):
        if self.necrosis_model is None:
            self.necrosis_model = self._load_model(self.cfg.get("necrosis_model_path"), "cpsam", "壊死用")
        return self.necrosis_model

    def _load_model(self, model_path, fallback_model, model_name):
        try:
            from cellpose.models import CellposeModel
            if model_path and os.path.exists(model_path):
                self._log(f"【{model_name}】カスタムモデルをロードします: {model_path}", metadata={"path": model_path})
                model = CellposeModel(gpu=self.device_available, pretrained_model=model_path)
                self._log(f"【{model_name}】カスタムモデルのロードが完了しました。")
                return model

            self._log(f"【{model_name}】デフォルトモデル（{fallback_model}）をロードします。")
            model = CellposeModel(gpu=self.device_available, model_type=fallback_model)
            self._log(f"【{model_name}】デフォルトモデルのロードが完了しました。")
            return model
        except Exception as e:
            self._log(f"【{model_name}】モデルの初期化失敗: {e}", LogCategory.ERROR)
            raise

    @staticmethod
    def _apply_clip(image, clip_val):
        val = float(clip_val)
        if val >= 255.0 or val <= 0: return image
        if image.dtype == np.uint16: val *= (65535.0 / 255.0)
        return np.minimum(image, val).astype(image.dtype)

    @staticmethod
    def _apply_gamma(image, gamma):
        g = float(gamma)
        if g == 1.0 or g <= 0: return image
        max_val = 65535.0 if image.dtype == np.uint16 else 255.0
        normalized = image.astype(np.float32) / max_val
        corrected = np.power(normalized, g)
        return np.clip(corrected * max_val, 0, max_val).astype(image.dtype)

    @staticmethod
    def _apply_cutoff(image, threshold, fade_width):
        th_val = float(threshold)
        w_val = float(fade_width)
        if th_val <= 0: return image
        max_val = 65535.0 if image.dtype == np.uint16 else 255.0
        if image.dtype == np.uint16:
            th_val *= (65535.0 / 255.0)
            w_val *= (65535.0 / 255.0)

        if w_val <= 0 or th_val <= (w_val / 2.0):
            _, img_clean = cv2.threshold(image, th_val, max_val, cv2.THRESH_TOZERO)
            return img_clean

        lower, upper = max(0.0, th_val - w_val / 2), min(max_val, th_val + w_val / 2)
        range_width = upper - lower
        img_float = image.astype(np.float32)
        t = np.clip((img_float - lower) / range_width, 0.0, 1.0)
        k = t * t * (3.0 - 2.0 * t)
        return (img_float * k).astype(image.dtype)

    @staticmethod
    def _filter_masks_by_intensity(masks, original_image, intensity_threshold):
        th_val = float(intensity_threshold)
        if th_val <= 0: return masks
        if original_image.dtype == np.uint16: th_val *= (65535.0 / 255.0)

        new_masks = np.zeros_like(masks)
        max_id = int(np.max(masks))
        current_new_id = 1
        for i in range(1, max_id + 1):
            mask_area = (masks == i)
            if not np.any(mask_area): continue
            if np.mean(original_image[mask_area]) >= th_val:
                new_masks[mask_area] = current_new_id
                current_new_id += 1
        return new_masks

    def analyze(self, bf_image, fl_image=None, pi_image=None, run_cell=True, run_lipid=True, run_necrosis=False, progress_callback=None):
        results, visuals = {}, {}

        # 1. 細胞解析
        cell_masks = None
        total_cell_px = 0
        if run_cell and bf_image is not None:
            if progress_callback: progress_callback(0.1)
            cell_masks, _, _ = self.get_cell_model().eval(
                bf_image, diameter=self.cfg.get("cell_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("cell_flow_threshold"),
                cellprob_threshold=self.cfg.get("cell_cellprob_threshold"),
                min_size=self.cfg.get("cell_min_size")
            )
            total_cell_px = int(np.sum(cell_masks > 0))
            results["cell_count"] = int(np.max(cell_masks))
            results["total_cell_px"] = total_cell_px
            visuals["cell"] = self._draw_masks(bf_image, cell_masks, True, self.cfg.get("cell_color"), salt=100)

        # 2. 油脂解析
        lipid_masks = None
        total_lipid_px = 0
        if run_lipid and fl_image is not None:
            if progress_callback: progress_callback(0.4)
            fl_clean = self._apply_clip(fl_image, self.cfg.get("fl_intensity_clip", 255.0))
            fl_clean = self._apply_gamma(fl_clean, self.cfg.get("fl_gamma", 1.0))
            fl_clean = self._apply_cutoff(fl_clean, self.cfg.get("fl_noise_cutoff", 10.0), self.cfg.get("fl_noise_fade_width", 0.0))
            visuals["lipid_clean"] = self._prepare_canvas(fl_clean)

            lipid_masks, _, _ = self.get_lipid_model().eval(
                fl_clean, diameter=self.cfg.get("lipid_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("lipid_flow_threshold"),
                cellprob_threshold=self.cfg.get("lipid_cellprob_threshold"),
                min_size=self.cfg.get("lipid_min_size")
            )
            lipid_masks = self._filter_masks_by_intensity(lipid_masks, fl_image, self.cfg.get("fl_intensity_threshold", 20.0))
            total_lipid_px = int(np.sum(lipid_masks > 0))
            results["lipid_count"] = int(np.max(lipid_masks))
            results["total_lipid_px"] = total_lipid_px
            visuals["lipid"] = self._draw_masks(fl_image, lipid_masks, False, self.cfg.get("lipid_color"), salt=200)

        # 3. 統合解析（油脂）
        if run_cell and run_lipid and cell_masks is not None and lipid_masks is not None:
            integrated_masks = np.where(cell_masks > 0, lipid_masks, 0)
            integrated_px = int(np.sum(integrated_masks > 0))
            cell_count = int(results.get("cell_count", 0))
            lipid_cell_ids = np.unique(cell_masks[np.logical_and(cell_masks > 0, lipid_masks > 0)])

            results["lipid_cell_ratio"] = integrated_px / total_cell_px if total_cell_px > 0 else 0.0
            results["total_production_ratio"] = total_lipid_px / total_cell_px if total_cell_px > 0 else 0.0
            results["intracellular_lipid_percent"] = integrated_px / total_lipid_px if total_lipid_px > 0 else 0.0
            results["extracellular_lipid_percent"] = (total_lipid_px - integrated_px) / total_lipid_px if total_lipid_px > 0 else 0.0
            results["lipid_positive_cell_count"] = int(len(lipid_cell_ids))
            results["lipid_positive_cell_ratio"] = results["lipid_positive_cell_count"] / cell_count if cell_count > 0 else 0.0

            visuals["combined"] = self._draw_combined(
                bf_image, cell_masks, lipid_masks,
                self.cfg.get("combined_cell_color"), self.cfg.get("combined_lipid_color"),
                cell_salt=100, sub_salt=200,
                highlight_flag=bool(self.cfg.get("highlight_lipid_negative_cells", 1.0))
            )

        # 4. 壊死解析
        necrosis_masks = None
        if run_necrosis and pi_image is not None:
            if progress_callback: progress_callback(0.7)
            pi_clean = self._apply_clip(pi_image, self.cfg.get("pi_intensity_clip", 255.0))
            pi_clean = self._apply_gamma(pi_clean, self.cfg.get("pi_gamma", 1.0))
            pi_clean = self._apply_cutoff(pi_clean, self.cfg.get("pi_noise_cutoff", 10.0), self.cfg.get("pi_noise_fade_width", 0.0))
            visuals["necrosis_clean"] = self._prepare_canvas(pi_clean)

            necrosis_masks, _, _ = self.get_necrosis_model().eval(
                pi_clean, diameter=self.cfg.get("necrosis_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("necrosis_flow_threshold"),
                cellprob_threshold=self.cfg.get("necrosis_cellprob_threshold"),
                min_size=self.cfg.get("necrosis_min_size")
            )
            necrosis_masks = self._filter_masks_by_intensity(necrosis_masks, pi_image, self.cfg.get("pi_intensity_threshold", 20.0))
            results["necrosis_count"] = int(np.max(necrosis_masks))
            results["total_necrosis_px"] = int(np.sum(necrosis_masks > 0))
            visuals["necrosis"] = self._draw_masks(pi_image, necrosis_masks, False, self.cfg.get("necrosis_color"), salt=300)

        # 5. 統合解析（壊死）
        if run_cell and run_necrosis and cell_masks is not None and necrosis_masks is not None:
            cell_count = int(results.get("cell_count", 0))
            necrosis_overlap_ratio = float(self.cfg.get("necrosis_overlap_ratio", 0.0))
            overlap_mask = np.logical_and(cell_masks > 0, necrosis_masks > 0)
            overlap_cells = cell_masks[overlap_mask]
            overlap_necrosis = necrosis_masks[overlap_mask]

            valid_ids = []
            if len(overlap_cells) > 0:
                cell_areas = np.bincount(cell_masks.ravel())
                max_nec_id = int(np.max(necrosis_masks))
                offset = int(max_nec_id + 1)
                comb = overlap_cells.astype(np.int64) * offset + overlap_necrosis.astype(np.int64)
                unq, cnt = np.unique(comb, return_counts=True)
                c_ids = (unq // offset).astype(int)
                valid_ids = np.unique(c_ids[cnt / cell_areas[c_ids] >= necrosis_overlap_ratio]).tolist()

            results["necrosis_positive_cell_count"] = len(valid_ids)
            results["necrosis_positive_cell_ratio"] = len(valid_ids) / cell_count if cell_count > 0 else 0.0
            visuals["combined_necrosis"] = self._draw_combined(
                bf_image, cell_masks, necrosis_masks,
                self.cfg.get("combined_cell_color"), self.cfg.get("combined_necrosis_color"),
                cell_salt=100, sub_salt=300,
                highlight_flag=bool(self.cfg.get("highlight_necrosis_negative_cells", 1.0)),
                positive_cell_ids=valid_ids
            )

        return results, visuals

    @staticmethod
    def _parse_color(color_str):
        if not color_str: return None
        try:
            c = str(color_str).strip()
            if "," in c:
                vals = [int(x.strip()) for x in c.split(",")]
                if len(vals) == 3 and all(0 <= v <= 255 for v in vals): return vals
            if c.startswith("#") and len(c) == 7:
                return [int(c[5:7], 16), int(c[3:5], 16), int(c[1:3], 16)]
        except:
            pass
        return None

    @staticmethod
    def _color_for_mask(mask_area, salt=0):
        y, x = np.where(mask_area)
        if len(y) == 0: return [128, 128, 128]
        seed = (int(np.mean(y)) * 1009 + int(np.mean(x)) * 137 + salt) % (2 ** 31 - 1)
        rng = np.random.default_rng(seed)
        return rng.integers(100, 255, size=3).tolist()

    @staticmethod
    def _prepare_canvas(img):
        canvas = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if len(img.shape) == 2 else img.copy()
        if canvas.dtype != np.uint8: canvas = cv2.normalize(canvas, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        return canvas

    def _draw_masks(self, img, masks, highlight_boundaries, color_str, salt=0):
        canvas = self._prepare_canvas(img)
        overlay, max_id = canvas.copy(), int(np.max(masks))
        base_color = self._parse_color(color_str)
        for i in range(1, max_id + 1):
            mask_area = (masks == i)
            if np.any(mask_area): overlay[mask_area] = base_color if base_color else self._color_for_mask(mask_area, salt)
        blended = cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0)
        if highlight_boundaries and max_id > 0: blended[find_boundaries(masks, mode='inner')] = [255, 255, 255]
        return blended

    def _draw_combined(self, img, cell_masks, sub_masks, cell_color_str, sub_color_str, cell_salt=100, sub_salt=200, highlight_flag=False, positive_cell_ids=None):
        canvas = self._prepare_canvas(img)
        max_cell_id, cell_color = int(np.max(cell_masks)), self._parse_color(cell_color_str)
        if max_cell_id > 0:
            bounds = find_boundaries(cell_masks, mode='inner')
            if cell_color:
                canvas[bounds] = cell_color
            else:
                for i in range(1, max_cell_id + 1):
                    mask_area = (cell_masks == i)
                    if np.any(mask_area): canvas[np.logical_and(bounds, mask_area)] = self._color_for_mask(mask_area, cell_salt)

        overlay, max_sub_id, sub_color = canvas.copy(), int(np.max(sub_masks)), self._parse_color(sub_color_str)
        for i in range(1, max_sub_id + 1):
            mask_area = (sub_masks == i)
            if np.any(mask_area): overlay[mask_area] = sub_color if sub_color else self._color_for_mask(mask_area, sub_salt)

        combined = cv2.addWeighted(overlay, 0.5, canvas, 0.5, 0)
        if highlight_flag and max_cell_id > 0:
            pos_ids = set(positive_cell_ids) if positive_cell_ids is not None else set(np.unique(cell_masks[np.logical_and(cell_masks > 0, sub_masks > 0)]).astype(int).tolist())
            for cid in range(1, max_cell_id + 1):
                if cid not in pos_ids:
                    cnts, _ = cv2.findContours((cell_masks == cid).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(combined, cnts, -1, [0, 0, 255], 3)
        return combined
