from __future__ import annotations

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, roc_auc_score
from torch.utils.data import DataLoader, TensorDataset

from tradex.config.settings import settings
from tradex.models.base import BaseModel


class _LSTMNet(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden_size, num_layers=num_layers, dropout=dropout, batch_first=True
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return torch.sigmoid(self.fc(out[:, -1, :]))


class LSTMModel(BaseModel):
    name = "lstm"

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        epochs: int = 30,
        batch_size: int = 32,
        lr: float = 1e-3,
    ):
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self._net: _LSTMNet | None = None

    def _to_sequences(self, X: pd.DataFrame) -> np.ndarray:
        seq_len = settings.lookback_periods
        arr = X.values.astype(np.float32)
        return np.stack([arr[i : i + seq_len] for i in range(len(arr) - seq_len)])

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        seqs = self._to_sequences(X)
        targets = np.asarray(y, dtype=np.float32)[settings.lookback_periods :]
        n = min(len(seqs), len(targets))
        seqs, targets = seqs[:n], targets[:n]

        self._net = _LSTMNet(seqs.shape[2], self.hidden_size, self.num_layers, self.dropout)
        loader = DataLoader(
            TensorDataset(torch.from_numpy(seqs), torch.from_numpy(targets).unsqueeze(1)),
            batch_size=self.batch_size,
            shuffle=False,
        )
        optimizer = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        criterion = nn.BCELoss()

        self._net.train()
        for _ in range(self.epochs):
            for xb, yb in loader:
                optimizer.zero_grad()
                criterion(self._net(xb), yb).backward()
                optimizer.step()

    def predict_proba(self, X: pd.DataFrame) -> float:
        assert self._net is not None, "Call fit() before predict_proba()."
        seqs = self._to_sequences(X)
        self._net.eval()
        with torch.no_grad():
            return float(self._net(torch.from_numpy(seqs[-1:])).item())

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
        assert self._net is not None
        seqs = self._to_sequences(X)
        targets = np.asarray(y, dtype=np.float32)[settings.lookback_periods :]
        n = min(len(seqs), len(targets))
        seqs, targets = seqs[:n], targets[:n]

        self._net.eval()
        with torch.no_grad():
            probas = self._net(torch.from_numpy(seqs)).squeeze().numpy()
        preds = (probas >= 0.5).astype(int)
        return {
            "accuracy": accuracy_score(targets, preds),
            "roc_auc": roc_auc_score(targets, probas),
        }
