"""离线训练脚本：数据生成 + 模型训练 + 保存。

用法：
    python ml_training/train.py --epochs 50 --batch-size 64 --version v2
"""
import argparse
import json
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

from app.ml.model import BehaviorLSTM, FocalLoss

# ──────────────────────────────────────────────
# 数据生成
# ──────────────────────────────────────────────

SEQ_LEN = 20
FEAT_DIM = 32


def _make_normal_sequence() -> np.ndarray:
    """生成正常用户行为序列。"""
    seq = []
    for _ in range(SEQ_LEN):
        vec = [0.0] * FEAT_DIM
        vec[0] = 0.0          # event_type: ACTION
        vec[2] = 1.0          # LOGIN
        # 正常工作时间（8-22 点）sin/cos
        h = random.uniform(8, 22)
        vec[5] = math.sin(2 * math.pi * h / 24)
        vec[6] = math.cos(2 * math.pi * h / 24)
        vec[9] = 0.0           # 不是新设备
        vec[10] = 0.0          # 不使用 VPN
        vec[11] = random.uniform(0, 0.05)   # 常驻地附近
        vec[14] = 1.0          # 中国 IP
        seq.append(vec)
    return np.array(seq, dtype=np.float32)


def _make_anomaly_sequence() -> np.ndarray:
    """生成异常用户行为序列（随机注入多种攻击模式）。"""
    seq = []
    anomaly_type = random.choice(["foreign_ip", "new_device_night", "vpn_rapid", "multi_country"])

    for i in range(SEQ_LEN):
        vec = [0.0] * FEAT_DIM
        if anomaly_type == "foreign_ip":
            vec[15] = 1.0      # 美国 IP
            vec[11] = 0.9      # 距家很远
        elif anomaly_type == "new_device_night":
            vec[9] = 1.0       # 新设备
            h = random.uniform(0, 6)    # 深夜
            vec[5] = math.sin(2 * math.pi * h / 24)
            vec[6] = math.cos(2 * math.pi * h / 24)
        elif anomaly_type == "vpn_rapid":
            vec[10] = 1.0      # VPN
            vec[13] = 0.05     # 极短操作间隔（可能是脚本）
        elif anomaly_type == "multi_country":
            vec[14] = 0.5      # 混合国家
            vec[15] = 0.5
            vec[11] = random.uniform(0.5, 1.0)
        seq.append(vec)
    return np.array(seq, dtype=np.float32)


def generate_dataset(n_normal: int = 8000, n_anomaly: int = 2000):
    """生成训练数据集（正常:异常 = 4:1）。"""
    X_normal = np.stack([_make_normal_sequence() for _ in range(n_normal)])
    X_anomaly = np.stack([_make_anomaly_sequence() for _ in range(n_anomaly)])

    X = np.concatenate([X_normal, X_anomaly], axis=0)
    y = np.array([0.0] * n_normal + [1.0] * n_anomaly, dtype=np.float32)

    # 打乱
    idx = np.random.permutation(len(X))
    return X[idx], y[idx]


# ──────────────────────────────────────────────
# 训练
# ──────────────────────────────────────────────

def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"训练设备: {device}")

    X, y = generate_dataset(n_normal=8000, n_anomaly=2000)
    X_tensor = torch.from_numpy(X)
    y_tensor = torch.from_numpy(y).unsqueeze(1)

    dataset = TensorDataset(X_tensor, y_tensor)
    val_size = int(len(dataset) * 0.2)
    train_ds, val_ds = random_split(dataset, [len(dataset) - val_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size)

    hyperparams = {
        "input_dim": FEAT_DIM,
        "hidden_dim": 256,
        "num_layers": 2,
        "dropout": 0.3,
        "seq_len": SEQ_LEN,
    }
    model = BehaviorLSTM(**{k: v for k, v in hyperparams.items() if k != "seq_len"})
    model = model.to(device)

    criterion = FocalLoss(alpha=0.25, gamma=2.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, args.epochs + 1):
        # 训练
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            prob, _ = model(xb)
            loss = criterion(prob, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(xb)
        train_loss /= len(train_ds)

        # 验证
        model.eval()
        val_loss = 0.0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                prob, _ = model(xb)
                val_loss += criterion(prob, yb).item() * len(xb)
                all_preds.extend(prob.cpu().numpy().flatten())
                all_labels.extend(yb.cpu().numpy().flatten())
        val_loss /= len(val_ds)
        scheduler.step()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 10 == 0 or epoch == 1:
            print(f"Epoch {epoch:3d}/{args.epochs} | train_loss={train_loss:.4f} | val_loss={val_loss:.4f}")

    # 计算最终指标
    preds_bin = [1 if p >= 0.5 else 0 for p in all_preds]
    labels_bin = [int(l) for l in all_labels]
    from sklearn.metrics import roc_auc_score, classification_report
    auc = roc_auc_score(labels_bin, all_preds)
    report = classification_report(labels_bin, preds_bin, output_dict=True)
    f1 = report.get("1", {}).get("f1-score", 0.0)

    print(f"\n最终结果: AUC={auc:.4f} | F1={f1:.4f} | val_loss={best_val_loss:.4f}")

    # 保存
    model_dir = Path(args.output_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    save_path = model_dir / f"lstm_{args.version}.pt"

    torch.save(
        {
            "model_state_dict": best_state,
            "hyperparams": hyperparams,
            "metrics": {
                "val_loss": best_val_loss,
                "auc_roc": auc,
                "f1_score": f1,
            },
            "version": args.version,
        },
        save_path,
    )
    print(f"模型已保存: {save_path}")
    return {"val_loss": best_val_loss, "auc_roc": auc, "f1_score": f1}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LSTM 异常检测模型训练")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--version", type=str, default="v1")
    parser.add_argument("--output-dir", type=str, default="./ml_training/models")
    args = parser.parse_args()
    train(args)
