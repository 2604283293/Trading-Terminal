"""选股筛选引擎 — 扫描全市场日线数据，按用户条件筛选标的。

数据来源：灵启数据 API 缓存（data/daily_dump/*.parquet），替代原 TDX .day 文件。
在 QThread 中运行，通过回调报告进度。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as DateType
from typing import Callable

import pandas as pd

from shared.local_store import load_daily_dump_range, list_cached_dates

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
    "ma5_pullback": {
        "label": "首次回踩5日线",
        "params": {"trend_days": 5, "clean_days": 2, "near_pct": 2.0},
        "hint": "上升趋势中首次回踩MA5。trend_days=趋势确认天数, clean_days=干净运行天数, near_pct=接近容差%",
    },
}


def _load_market_data(as_of_date: DateType, min_history: int = 60) -> pd.DataFrame:
    """从 API 缓存加载全市场日线数据。

    返回包含最近 min_history 个交易日（截至 as_of_date）的全部股票日线 DataFrame。
    列: stock_code, date, open, high, low, close, volume, amount
    """
    df = load_daily_dump_range(as_of_date, min_days=min_history)
    if df.empty:
        return df
    # 确保必需的列存在
    required = ["stock_code", "date", "open", "high", "low", "close", "volume", "amount"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame(columns=required)
    return df


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

    elif ctype == "ma5_pullback":
        trend_days = params.get("trend_days", 10)
        near_pct = params.get("near_pct", 2.0)
        clean_days = params.get("clean_days", 3)
        if len(df) < trend_days + 5:
            return False

        ma5 = df["close"].rolling(5).mean()
        today_ma5 = ma5.iloc[-1]
        if today_ma5 <= 0:
            return False

        # ── 1. 确认上升趋势 ──
        recent_ma5 = ma5.iloc[-trend_days:]
        recent_close = df["close"].iloc[-trend_days:]

        # 均线斜率向上 (用中段 vs 起点的中值比较，排除单日毛刺)
        mid = len(recent_ma5) // 2
        if recent_ma5.iloc[-1] <= recent_ma5.iloc[mid]:
            return False

        # 大部分交易日收盘在 MA5 上方
        above_count = (recent_close.values > recent_ma5.values).sum()
        if above_count < int(trend_days * 0.6):
            return False

        # ── 2. 近期站稳 MA5 上方 —— 用收盘价判断，允许盘中波动 ──
        for offset in range(1, clean_days + 1):
            ma5_val = ma5.iloc[-offset]
            if ma5_val <= 0:
                return False
            # 收盘价必须明确高于 MA5（超过容差），不算回踩
            if df["close"].iloc[-offset] <= ma5_val * (1 + near_pct / 100):
                return False

        # ── 3. 今日首次回踩 —— 开盘或盘中触及 MA5（容差内） ──
        nearest_today = min(today["open"], today["low"])
        dist_pct = (nearest_today - today_ma5) / today_ma5 * 100
        return dist_pct <= near_pct

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
    as_of_date: DateType | None = None,
) -> list[ScanResult]:
    """执行全市场扫描。

    数据来源：API 缓存（data/daily_dump/*.parquet）。

    Args:
        conditions: 条件列表，每条为 {"type": ..., "params": {...}}
        on_progress: 进度回调 (current, total, current_code)
        market_filter: "sh" | "sz" | "bj" | "all"
        as_of_date: 历史回溯日期。None = 使用最新缓存日期。

    Returns:
        匹配的 ScanResult 列表
    """
    results: list[ScanResult] = []

    cached_dates = list_cached_dates()
    scan_date = as_of_date or (cached_dates[-1] if cached_dates else DateType.today())

    # 过滤市场：从 stock_code 后缀判断
    market_map = {"sh": ".SH", "sz": ".SZ", "bj": ".BJ"}
    if market_filter == "all":
        market_suffix = None
    else:
        market_suffix = market_map.get(market_filter, "")

    # ── 加载全市场历史数据 ──
    market_df = _load_market_data(scan_date, min_history=60)
    if market_df.empty:
        return results

    # 按日期截断
    cutoff = pd.Timestamp(scan_date)
    market_df = market_df[market_df["date"] <= cutoff]

    # 按股票分组
    grouped = market_df.groupby("stock_code")
    codes = list(grouped.groups.keys())

    # 市场筛选
    if market_suffix:
        codes = [c for c in codes if c.endswith(market_suffix)]

    total = len(codes)
    for idx, code in enumerate(codes):
        if on_progress:
            on_progress(idx + 1, total, code)

        stock_df = grouped.get_group(code).sort_values("date").reset_index(drop=True)
        if len(stock_df) < 2:
            continue

        match = True
        reasons = []
        for cond in conditions:
            try:
                if not _check_condition(stock_df, cond):
                    match = False
                    break
                reasons.append(CONDITION_TYPES[cond["type"]]["label"])
            except Exception:
                match = False
                break

        if match:
            metrics = _compute_metrics(stock_df)
            results.append(ScanResult(code=code, metrics=metrics, match_reasons=reasons))

    return results
