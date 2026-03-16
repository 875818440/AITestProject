"""LSTM 推理引擎 — 线程安全的单例，支持模型热加载。"""
import os
import threading
from pathlib import Path

import numpy as np
import torch

from app.core.config import settings
from app.core.logging import get_logger
from app.ml.model import BehaviorLSTM

logger = get_logger(__name__)


class LSTMPredictor:
    """线程安全的 LSTM 推理引擎（单例）。"""

    _instance: "LSTMPredictor | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._model: BehaviorLSTM | None = None
        self._model_version: str | None = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._infer_lock = threading.Lock()
        logger.info("推理引擎初始化", device=str(self._device))

    @classmethod
    def get_instance(cls) -> "LSTMPredictor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance.load_model()
        return cls._instance

    def load_model(self, version: str | None = None) -> bool:
        """从磁盘加载模型权重，支持热加载（不中断服务）。"""
        version = version or settings.model_version
        model_path = Path(settings.model_path) / f"lstm_{version}.pt"

        if not model_path.exists():
            logger.warning("模型文件不存在，使用随机初始化权重（仅用于开发）", path=str(model_path))
            model = BehaviorLSTM()
            model.eval()
            with self._infer_lock:
                self._model = model.to(self._device)
                self._model_version = f"{version}_random"
            return False

        try:
            checkpoint = torch.load(model_path, map_location=self._device, weights_only=True)
            hyperparams = checkpoint.get("hyperparams", {})
            model = BehaviorLSTM(
                input_dim=hyperparams.get("input_dim", 32),
                hidden_dim=hyperparams.get("hidden_dim", 256),
                num_layers=hyperparams.get("num_layers", 2),
                dropout=0.0,  # 推理时关闭 dropout
            )
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()

            with self._infer_lock:
                self._model = model.to(self._device)
                self._model_version = version

            logger.info("模型加载成功", version=version, path=str(model_path))
            return True
        except Exception as exc:
            logger.error("模型加载失败", version=version, error=str(exc))
            return False

    def predict(self, sequence: np.ndarray) -> tuple[float, list[float]]:
        """
        推理单条行为序列。

        Args:
            sequence: numpy 数组，形状 (seq_len, feature_dim)

        Returns:
            (anomaly_prob, attention_weights)
        """
        if self._model is None:
            logger.error("模型未初始化")
            return 0.0, []

        with self._infer_lock:
            with torch.no_grad():
                x = torch.tensor(sequence, dtype=torch.float32)
                x = x.unsqueeze(0).to(self._device)  # (1, seq_len, feat_dim)
                prob, attn = self._model(x)
                anomaly_prob = float(prob.squeeze().cpu().item())
                attn_weights = attn.squeeze().cpu().tolist()
                if isinstance(attn_weights, float):
                    attn_weights = [attn_weights]
        return anomaly_prob, attn_weights

    @property
    def model_version(self) -> str | None:
        return self._model_version


predictor = LSTMPredictor.get_instance()
