import torch
import numpy as np
import os
import cv2
import logging
from cellpose.models import CellposeModel
from skimage.segmentation import find_boundaries


class YeastAnalyzer:
    """
    透過光(BF)と蛍光(FL)画像を解析し、細胞数および油脂の生産・分布を定量化する。
    """

    def __init__(self, config):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.cfg = config
        self.device_available = torch.cuda.is_available() and bool(config.get("use_gpu"))
        # デバイスの優先順位: CUDA (Win/Linux) > MPS (Mac) > CPU
        if torch.cuda.is_available():
            self.device = "cuda"
            # 最新の計算最適化をすべて「物理的に」オフにする
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = False
            # 演算を最も原始的で確実な FP32 (Single Precision) に固定
            torch.set_float32_matmul_precision('highest')
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        self.logger.info(f"解析デバイス: {self.device}")

        # CellposeModelの初期化 (gpu=Trueにすると、torchが対応していれば自動でMPSが使われます)
        self.cell_model = self._load_model(config.get("cell_model_path"), 'cyto2', "細胞用")
        self.lipid_model = self._load_model(config.get("lipid_model_path"), 'cyto2', "油脂用")

    def _load_model(self, model_path, fallback_model, model_name):
        try:
            if model_path and os.path.exists(model_path):
                return CellposeModel(gpu=self.device_available, pretrained_model=model_path)
            return CellposeModel(gpu=self.device_available, model_type=fallback_model)
        except Exception as e:
            self.logger.error(f"{model_name}モデルの初期化失敗: {e}")
            return CellposeModel(gpu=self.device_available, model_type=fallback_model)

    def analyze(self, bf_image, fl_image, run_cell=True, run_lipid=True, progress_callback=None):
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
            if progress_callback: progress_callback(0.5)
            lipid_masks, _, _ = self.lipid_model.eval(
                fl_image, diameter=self.cfg.get("lipid_diameter"), channels=[0, 0],
                flow_threshold=self.cfg.get("lipid_flow_threshold"),
                cellprob_threshold=self.cfg.get("lipid_cellprob_threshold"),
                min_size=self.cfg.get("lipid_min_size")
            )
            total_lipid_px = int(np.sum(lipid_masks > 0))
            results["lipid_count"] = int(np.max(lipid_masks))
            results["total_lipid_px"] = total_lipid_px
            visuals["lipid"] = self._draw_masks(fl_image, lipid_masks, False, self.cfg.get("lipid_color"))

        # 3. 統合解析（両方のフラグがONの場合のみ実行）
        if run_cell and run_lipid and cell_masks is not None and lipid_masks is not None:
            integrated_masks = np.where(cell_masks > 0, lipid_masks, 0)
            integrated_px = int(np.sum(integrated_masks > 0))
            extracellular_px = total_lipid_px - integrated_px

            results["lipid_cell_ratio"] = integrated_px / total_cell_px if total_cell_px > 0 else 0.0
            results["total_production_ratio"] = total_lipid_px / total_cell_px if total_cell_px > 0 else 0.0
            results["intracellular_lipid_percent"] = integrated_px / total_lipid_px if total_lipid_px > 0 else 0.0
            results["extracellular_lipid_percent"] = extracellular_px / total_lipid_px if total_lipid_px > 0 else 0.0
            results["integrated_lipid_px"] = integrated_px
            results["extracellular_lipid_px"] = extracellular_px

            visuals["combined"] = self._draw_combined(
                bf_image, cell_masks, lipid_masks,
                self.cfg.get("combined_cell_color"), self.cfg.get("combined_lipid_color")
            )
        return results, visuals

    def _parse_color(self, color_str):
        if not color_str: return None
        try:
            c = str(color_str).strip()
            if "," in c: return [int(x.strip()) for x in c.split(",")]
            if c.startswith("#") and len(c) == 7:
                return [int(c[5:7], 16), int(c[3:5], 16), int(c[1:3], 16)]
        except:
            return None
        return None

    def _prepare_canvas(self, img):
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
                color = base_color if base_color is not None else np.random.randint(100, 255, 3).tolist()
                overlay[masks == i] = color
        blended = cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0)
        if highlight_boundaries and max_id > 0:
            blended[find_boundaries(masks, mode='inner')] = [255, 255, 255]
        return blended

    def _draw_combined(self, img, cell_masks, lipid_masks, cell_color_str, lipid_color_str):
        canvas = self._prepare_canvas(img)
        max_cell_id = int(np.max(cell_masks))
        cell_color = self._parse_color(cell_color_str)
        if max_cell_id > 0:
            bounds = find_boundaries(cell_masks, mode='inner')
            if cell_color is not None:
                canvas[bounds] = cell_color
            else:
                for i in range(1, max_cell_id + 1):
                    canvas[np.logical_and(bounds, cell_masks == i)] = np.random.randint(100, 255, 3).tolist()
        overlay = canvas.copy()
        max_lipid_id = int(np.max(lipid_masks))
        lipid_color = self._parse_color(lipid_color_str)
        if max_lipid_id > 0:
            for i in range(1, max_lipid_id + 1):
                color = lipid_color if lipid_color is not None else np.random.randint(100, 255, 3).tolist()
                overlay[lipid_masks == i] = color
        return cv2.addWeighted(overlay, 0.5, canvas, 0.5, 0)