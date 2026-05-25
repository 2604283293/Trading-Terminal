"""模拟 K 线数据 — TDX 真实数据到位前用于 UI 调试"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_mock_klines(
    n: int = 200,
    start_price: float = 100.0,
    seed: int = 42,
    end_date: str = "2026-05-25",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0005, scale=0.02, size=n)
    closes = start_price * np.exp(np.cumsum(returns))
    opens = np.empty(n)
    opens[0] = start_price
    opens[1:] = closes[:-1]
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.015, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.015, n))
    volumes = rng.integers(low=100_000, high=2_000_000, size=n)
    dates = pd.date_range(end=end_date, periods=n, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
