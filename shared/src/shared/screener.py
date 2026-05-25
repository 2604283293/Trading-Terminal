"""选股筛选引擎 — 扫描全部 TDX 日线数据，按用户条件筛选标的。

在 QThread 中运行，通过回调报告进度。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import date as DateType, datetime, timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

# shared/src/shared/screener.py → parents[3] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_VIPDOC = _PROJECT_ROOT / "vipdoc"

# 条件类型 → 中文标签
CONDITION_TYPES: dict[str, dict] = {
    "daily_change": {
        "label": "日涨跌幅",
        "params": {"min_pct": -10.0, "max_pct": 10.0},
        "hint": "今日涨跌幅范围（%）",
    },
    "n_day_change": {
        "label": "N日涨跌幅",
        "params": {"days": 5, "min_pct": 0.0},
        "hint": "最近N日累计涨跌幅（%）",
    },
    "volume_ratio": {
        "label": "成交量放量",
        "params": {"days": 5, "min_ratio": 1.5},
        "hint": "今日成交量 / N日均量 的倍数下限",
    },
    "consecutive_days": {
        "label": "连续K线",
        "params": {"min_days": 3, "direction": "阳线"},
        "hint": "连续阳线/阴线天数下限，direction: 阳线|阴线",
    },
    "price_range": {
        "label": "价格范围",
        "params": {"min_price": 0.0, "max_price": 100.0},
        "hint": "最新收盘价区间",
    },
    "n_day_high": {
        "label": "N日新高",
        "params": {"days": 20},
        "hint": "今日收盘创N日新高",
    },
    "n_day_low": {
        "label": "N日新低",
        "params": {"days": 20},
        "hint": "今日收盘创N日新低",
    },
    "avg_volume": {
        "label": "日均成交额",
        "params": {"days": 5, "min_amount": 1e8},
        "hint": "N日均成交额下限（元），如 1e8 = 1亿",
    },
    "ma_cross": {
        "label": "均线交叉",
        "params": {"short": 5, "long": 20, "direction": "up"},
        "hint": "短期均线上穿/下穿长期均线，direction: up|down",
    },
    "gap": {
        "label": "跳空缺口",
        "params": {"direction": "up", "min_pct": 1.0},
        "hint": "今日最低价 > 昨日最高价(向上)/今日最高价 < 昨日最低价(向下)，min_pct 为缺口幅度下限",
    },
    "engulfing": {
        "label": "K线反包",
        "params": {"direction": "bullish"},
        "hint": "看涨反包：昨阴今阳，今日实体完全吞没昨日实体；看跌反包反之。direction: bullish|bearish",
    },
}


def _read_daily_raw(path: Path) -> pd.DataFrame | None:
    """快速读取 .day 文件为 DataFrame，不做任何验证。"""
    try:
        data = path.read_bytes()
        n = len(data) // 32
        if n == 0:
            return None
        records = []
        for i in range(n):
            rec = data[i * 32 : (i + 1) * 32]
            date_int, op, hi, lo, cl, amt, vol, _res = struct.unpack("=I I I I I f I I", rec)
            records.append({
                "date": date_int,
                "open": op / 100.0,
                "high": hi / 100.0,
                "low": lo / 100.0,
                "close": cl / 100.0,
                "amount": amt,
                "volume": vol,
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df
    except Exception:
        return None


def _check_condition(df: pd.DataFrame, cond: dict) -> bool:
    """检查单只股票是否满足某条条件。"""
    ctype = cond["type"]
    params = cond.get("params", {})

    if len(df) < 2:
        return False

    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    if ctype == "daily_change":
        if yesterday["close"] == 0:
            return False
        pct = (today["close"] - yesterday["close"]) / yesterday["close"] * 100
        lo = params.get("min_pct", -10)
        hi = params.get("max_pct", 10)
        return lo <= pct <= hi

    elif ctype == "n_day_change":
        n = params.get("days", 5)
        if len(df) < n + 1:
            return False
        base = df.iloc[-n - 1]["close"]
        if base == 0:
            return False
        pct = (today["close"] - base) / base * 100
        return pct >= params.get("min_pct", 0)

    elif ctype == "volume_ratio":
        n = params.get("days", 5)
        if len(df) < n + 1:
            return False
        avg_vol = df["volume"].iloc[-n - 1 : -1].mean()
        if avg_vol == 0:
            return False
        ratio = today["volume"] / avg_vol
        return ratio >= params.get("min_ratio", 1.5)

    elif ctype == "consecutive_days":
        direction = params.get("direction", "阳线")
        min_days = params.get("min_days", 3)
        closes = df["close"].values
        opens = df["open"].values
        count = 0
        for i in range(len(df) - 1, -1, -1):
            if direction == "阳线" and closes[i] >= opens[i]:
                count += 1
            elif direction == "阴线" and closes[i] < opens[i]:
                count += 1
            else:
                break
        return count >= min_days

    elif ctype == "price_range":
        lo = params.get("min_price", 0)
        hi = params.get("max_price", 100)
        return lo <= today["close"] <= hi

    elif ctype == "n_day_high":
        n = params.get("days", 20)
        if len(df) < n:
            return False
        recent_high = df["close"].iloc[-n - 1 : -1].max()
        return today["close"] > recent_high

    elif ctype == "n_day_low":
        n = params.get("days", 20)
        if len(df) < n:
            return False
        recent_low = df["close"].iloc[-n - 1 : -1].min()
        return today["close"] < recent_low

    elif ctype == "avg_volume":
        n = params.get("days", 5)
        if len(df) < n:
            return False
        avg_amt = df["amount"].iloc[-n:].mean()
        return avg_amt >= params.get("min_amount", 1e8)

    elif ctype == "ma_cross":
        short_n = params.get("short", 5)
        long_n = params.get("long", 20)
        direction = params.get("direction", "up")
        if len(df) < long_n + 1:
            return False
        ma_short_today = df["close"].iloc[-short_n:].mean()
        ma_long_today = df["close"].iloc[-long_n:].mean()
        ma_short_yest = df["close"].iloc[-short_n - 1 : -1].mean()
        ma_long_yest = df["close"].iloc[-long_n - 1 : -1].mean()
        if direction == "up":
            return ma_short_yest <= ma_long_yest and ma_short_today > ma_long_today
        else:
            return ma_short_yest >= ma_long_yest and ma_short_today < ma_long_today

    elif ctype == "gap":
        direction = params.get("direction", "up")
        min_pct = params.get("min_pct", 1.0)
        if direction == "up":
            if yesterday["high"] == 0:
                return False
            gap_pct = (today["low"] - yesterday["high"]) / yesterday["high"] * 100
            return gap_pct >= min_pct
        else:
            if yesterday["low"] == 0:
                return False
            gap_pct = (yesterday["low"] - today["high"]) / yesterday["low"] * 100
            return gap_pct >= min_pct

    elif ctype == "engulfing":
        direction = params.get("direction", "bullish")
        yest_open = yesterday["open"]
        yest_close = yesterday["close"]
        today_open = today["open"]
        today_close = today["close"]
        if direction == "bullish":
            # 昨阴线(收盘<开盘) + 今阳线(收盘>开盘) + 今日实体完全吞没昨日实体
            if not (yest_close < yest_open and today_close > today_open):
                return False
            return today_open <= yest_close and today_close >= yest_open
        else:
            # 昨阳线(收盘>开盘) + 今阴线(收盘<开盘) + 今日实体完全吞没昨日实体
            if not (yest_close > yest_open and today_close < today_open):
                return False
            return today_open >= yest_close and today_close <= yest_open

    return False


def _compute_metrics(df: pd.DataFrame) -> dict:
    """计算股票的常用指标，用于结果展示。"""
    today = df.iloc[-1]
    yesterday = df.iloc[-2] if len(df) > 1 else today

    daily_pct = 0.0
    if yesterday["close"] > 0:
        daily_pct = (today["close"] - yesterday["close"]) / yesterday["close"] * 100

    vol_5 = df["volume"].iloc[-6:-1].mean() if len(df) >= 6 else df["volume"].iloc[:-1].mean()
    vol_ratio = today["volume"] / vol_5 if vol_5 > 0 else 1.0

    ma5 = df["close"].iloc[-5:].mean() if len(df) >= 5 else today["close"]
    ma20 = df["close"].iloc[-20:].mean() if len(df) >= 20 else today["close"]

    n_day_high_20 = df["close"].iloc[-21:-1].max() if len(df) >= 21 else today["close"]

    return {
        "date": today["date"].strftime("%Y-%m-%d") if hasattr(today["date"], "strftime") else str(today["date"])[:10],
        "close": round(today["close"], 2),
        "change_pct": round(daily_pct, 2),
        "volume_ratio": round(vol_ratio, 2),
        "amount": today["amount"],
        "volume": int(today["volume"]),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "high_20": round(n_day_high_20, 2),
    }


@dataclass
class ScanResult:
    code: str
    metrics: dict
    match_reasons: list[str] = field(default_factory=list)


def run_screen(
    conditions: list[dict],
    on_progress: Callable[[int, int, str], None] | None = None,
    market_filter: str = "all",
) -> list[ScanResult]:
    """执行全市场扫描。

    Args:
        conditions: 条件列表，每条为 {"type": ..., "params": {...}}
        on_progress: 进度回调 (current, total, current_code)
        market_filter: "sh" | "sz" | "bj" | "all"

    Returns:
        匹配的 ScanResult 列表
    """
    results: list[ScanResult] = []

    markets = ["sh", "sz", "bj"] if market_filter == "all" else [market_filter]
    file_list: list[tuple[str, Path]] = []
    for mkt in markets:
        lday_dir = _VIPDOC / mkt / "lday"
        if not lday_dir.exists():
            continue
        for f in lday_dir.iterdir():
            if f.suffix == ".day":
                file_list.append((f.stem, f))

    total = len(file_list)
    for idx, (code, path) in enumerate(file_list):
        if on_progress:
            on_progress(idx + 1, total, code)

        df = _read_daily_raw(path)
        if df is None or len(df) < 5:
            continue

        match = True
        reasons = []
        for cond in conditions:
            try:
                if not _check_condition(df, cond):
                    match = False
                    break
                reasons.append(CONDITION_TYPES[cond["type"]]["label"])
            except Exception:
                match = False
                break

        if match:
            metrics = _compute_metrics(df)
            results.append(ScanResult(code=code, metrics=metrics, match_reasons=reasons))

    return results
