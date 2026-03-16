"""LSTM + Attention 异常检测模型（PyTorch）。"""
import torch
import torch.nn as nn


class AttentionLayer(nn.Module):
    """自注意力机制：对 LSTM 输出序列加权求和。"""

    def __init__(self, hidden_dim: int):
        super().__init__()
        self.attention = nn.Linear(hidden_dim, 1)

    def forward(self, lstm_out: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # lstm_out: (batch, seq_len, hidden_dim)
        scores = self.attention(lstm_out)          # (batch, seq_len, 1)
        weights = torch.softmax(scores, dim=1)     # (batch, seq_len, 1)
        context = (weights * lstm_out).sum(dim=1)  # (batch, hidden_dim)
        return context, weights.squeeze(-1)


class BehaviorLSTM(nn.Module):
    """
    双层 LSTM + Attention 异常行为检测模型。

    输入：(batch, seq_len, input_dim)
    输出：(batch, 1) — 异常概率（0~1）
    """

    def __init__(
        self,
        input_dim: int = 32,
        hidden_dim: int = 256,
        num_layers: int = 2,
        dropout: float = 0.3,
        fc_dims: tuple[int, ...] = (128, 64),
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=False,
        )
        self.attention = AttentionLayer(hidden_dim)
        self.dropout = nn.Dropout(dropout)

        # 全连接分类头
        layers = []
        in_dim = hidden_dim
        for out_dim in fc_dims:
            layers += [nn.Linear(in_dim, out_dim), nn.ReLU(), nn.Dropout(dropout)]
            in_dim = out_dim
        layers.append(nn.Linear(in_dim, 1))
        self.fc = nn.Sequential(*layers)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        # x: (batch, seq_len, input_dim)
        lstm_out, _ = self.lstm(x)                        # (batch, seq_len, hidden)
        context, attn_weights = self.attention(lstm_out)  # (batch, hidden)
        context = self.dropout(context)
        logits = self.fc(context)                         # (batch, 1)
        prob = torch.sigmoid(logits)
        return prob, attn_weights


class FocalLoss(nn.Module):
    """Focal Loss — 缓解正负样本极度不均衡问题。"""

    def __init__(self, alpha: float = 0.25, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        bce = nn.functional.binary_cross_entropy(pred, target, reduction="none")
        pt = torch.where(target == 1, pred, 1 - pred)
        focal_weight = self.alpha * (1 - pt) ** self.gamma
        return (focal_weight * bce).mean()
