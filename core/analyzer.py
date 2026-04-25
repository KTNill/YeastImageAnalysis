# Cellpose/PyTorch logic
import torch
import logging

class YeastAnalyzer:
    """
    酵母の顕微鏡画像から細胞検出および油脂占有率の解析を行うクラス。
    """
    def __init__(self, model_type='cyto', use_gpu=True):
        # ロギング設定
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # CUDAの利用可能性確認
        self.device_available = torch.cuda.is_available()
        if use_gpu and not self.device_available:
            self.logger.warning("警告: GPUが利用可能と設定されましたが、検出されませんでした。CPUモードで動作します。")
