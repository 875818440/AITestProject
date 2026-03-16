"""单元测试：LSTM 模型（仅验证形状，不依赖训练权重）。"""
import pytest
import torch
import numpy as np

from app.ml.model import BehaviorLSTM, AttentionLayer, FocalLoss


class TestAttentionLayer:
    def test_output_shape(self):
        attn = AttentionLayer(hidden_dim=64)
        lstm_out = torch.randn(4, 10, 64)   # (batch=4, seq=10, hidden=64)
        context, weights = attn(lstm_out)
        assert context.shape == (4, 64)
        assert weights.shape == (4, 10)

    def test_attention_weights_sum_to_one(self):
        attn = AttentionLayer(hidden_dim=32)
        lstm_out = torch.randn(2, 5, 32)
        _, weights = attn(lstm_out)
        sums = weights.sum(dim=1)
        assert torch.allclose(sums, torch.ones(2), atol=1e-5)


class TestBehaviorLSTM:
    def test_forward_output_shape(self):
        model = BehaviorLSTM(input_dim=32, hidden_dim=64, num_layers=2)
        x = torch.randn(8, 20, 32)   # (batch=8, seq=20, feat=32)
        prob, attn = model(x)
        assert prob.shape == (8, 1)
        assert attn.shape == (8, 20)

    def test_output_probability_range(self):
        model = BehaviorLSTM(input_dim=32, hidden_dim=64, num_layers=1)
        x = torch.randn(16, 20, 32)
        prob, _ = model(x)
        assert (prob >= 0).all() and (prob <= 1).all()

    def test_inference_no_grad(self):
        model = BehaviorLSTM(input_dim=32, hidden_dim=64, num_layers=1)
        model.eval()
        x = torch.randn(1, 20, 32)
        with torch.no_grad():
            prob, _ = model(x)
        assert prob.shape == (1, 1)


class TestFocalLoss:
    def test_loss_positive_class(self):
        criterion = FocalLoss()
        pred = torch.tensor([[0.9], [0.8]])
        target = torch.tensor([[1.0], [1.0]])
        loss = criterion(pred, target)
        assert loss.item() >= 0

    def test_loss_decreases_with_better_predictions(self):
        criterion = FocalLoss()
        good_pred = torch.tensor([[0.95], [0.05]])
        bad_pred = torch.tensor([[0.5], [0.5]])
        target = torch.tensor([[1.0], [0.0]])
        good_loss = criterion(good_pred, target)
        bad_loss = criterion(bad_pred, target)
        assert good_loss.item() < bad_loss.item()

    def test_perfect_prediction_near_zero_loss(self):
        criterion = FocalLoss()
        pred = torch.tensor([[0.9999], [0.0001]])
        target = torch.tensor([[1.0], [0.0]])
        loss = criterion(pred, target)
        assert loss.item() < 0.01
