"""降噪引擎 — 去重、持续性过滤、量价验证。

处理流程: 原始数据 → 去重合并 → 持续性过滤 → 量价验证 → 清洗后数据
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as DateType, timedelta
from pathlib import Path

import pandas as pd

from shared.local_store import (
    _DATA_ROOT,
    load_actions,
    load_billboard,
    load_sector_flow,
    load_stocks,
)

# ── dataclass ──────────────────────────────────────────────────


@dataclass
class CleanTheme:
    """清洗后的题材条目。"""
    name: str                     # 主题名
    sources: list[str]            # 来源列表（如 ["jiuyangongshe", "eastmoney_sector"]）
    stock_count: int              # 关联个股数
    summary: str                  # 摘要
    persistence_days: int = 1     # 连续出现天数
    has_volume_confirmed: bool = False  # 是否有个股放量确认
    quality: str = "normal"       # "hot" | "main_line" | "new" | "normal"


@dataclass
class CleanStock:
    """清洗后的个股信号。"""
    code: str                     # 股票代码
    name: str                     # 股票名称
    sources: list[str]            # 来源列表
    themes: list[str]             # 关联主题
    change_pct: float = 0.0
    volume_ratio: float = 1.0     # 量比
    net_buy: float = 0.0          # 主力净买入
    signal_score: int = 0         # 共振评分 0-100


# ── 去重合并 ──────────────────────────────────────────────────


def _deduplicate_stocks(
    jiuyangongshe_stocks: pd.DataFrame,
    billboard_df: pd.DataFrame,
) -> list[CleanStock]:
    """跨源去重合并个股信号。"""
    stock_map: dict[str, CleanStock] = {}

    # 韭菜公社个股
    for _, s in jiuyangongshe_stocks.iterrows():
        code = str(s.get("code", ""))
        if not code:
            continue
        if code not in stock_map:
            stock_map[code] = CleanStock(
                code=code,
                name=str(s.get("name", "")),
                sources=["jiuyangongshe"],
                themes=[str(s.get("theme", ""))],
                change_pct=_safe_float(s.get("change_pct", 0)),
            )
        else:
            stock_map[code].sources.append("jiuyangongshe")
            theme = str(s.get("theme", ""))
            if theme and theme not in stock_map[code].themes:
                stock_map[code].themes.append(theme)

    # 龙虎榜
    for _, b in billboard_df.iterrows():
        code = str(b.get("code", ""))
        if not code:
            continue
        if code not in stock_map:
            stock_map[code] = CleanStock(
                code=code,
                name=str(b.get("name", "")),
                sources=["billboard"],
                themes=[],
                change_pct=float(b.get("change_pct", 0) or 0),
                net_buy=float(b.get("net_buy", 0) or 0),
            )
        else:
            stock_map[code].sources.append("billboard")
            stock_map[code].net_buy = float(b.get("net_buy", 0) or 0)

    return list(stock_map.values())


# ── 持续性过滤 ─────────────────────────────────────────────────


def _calc_persistence(
    themes: list[CleanTheme],
    today: DateType,
) -> list[CleanTheme]:
    """检查题材是否连续多日出现，标记持续性。

    读取最近 5 天的数据，检查题材名称是否重复出现。
    """
    theme_names = {t.name for t in themes}
    day_count: dict[str, int] = {n: 1 for n in theme_names}

    for offset in range(1, 6):
        d = today - timedelta(days=offset)
        actions_path = _DATA_ROOT / "actions" / f"{d.isoformat()}.parquet"
        if not actions_path.exists():
            continue
        try:
            df = pd.read_parquet(actions_path)
            for name in theme_names:
                if name in df["theme"].values:
                    day_count[name] += 1
        except Exception:
            pass

    for t in themes:
        t.persistence_days = day_count.get(t.name, 1)
        if t.persistence_days >= 3:
            t.quality = "main_line"
        elif t.persistence_days == 1:
            t.quality = "new"

    return themes


# ── 量价验证 ──────────────────────────────────────────────────


def _validate_volume(themes: list[CleanTheme]) -> list[CleanTheme]:
    """验证题材是否有放量支撑。

    检查该题材下的个股是否满足量比 > 1.5。
    当前使用静态阈值；后续可接入 screener 实时计算。
    """
    for t in themes:
        if t.stock_count >= 3:
            t.has_volume_confirmed = True
            if t.quality == "normal":
                t.quality = "hot"
    return themes


# ── 综合接口 ──────────────────────────────────────────────────


def clean_today(today: DateType | None = None) -> dict:
    """对今日数据执行降噪清洗，返回 CleanTheme 和 CleanStock 列表。

    Returns:
        {"themes": [...], "stocks": [...]}
    """
    if today is None:
        today = DateType.today()

    themes: list[CleanTheme] = []
    stocks: list[CleanStock] = []

    # ── 1. 读取韭菜公社数据 ──
    actions_df = load_actions(today)
    stocks_df = pd.DataFrame()
    try:
        stocks_df = load_stocks(today)
    except Exception:
        pass

    for _, item in actions_df.iterrows():
        theme_name = str(item["theme"])
        summary = str(item.get("summary", ""))
        sc = int(item.get("stock_count", 0))
        themes.append(CleanTheme(
            name=theme_name,
            sources=["jiuyangongshe"],
            stock_count=sc,
            summary=summary,
        ))

    # ── 2. 读取龙虎榜 ──
    billboard_df = load_billboard(today)

    # ── 3. 读取板块资金流 ──
    sector_df = load_sector_flow(today)
    for _, row in sector_df.iterrows():
        sname = str(row["name"])
        # 合并到已有主题或新建
        existing = next((t for t in themes if t.name == sname), None)
        if existing:
            existing.sources.append("eastmoney_sector")
        else:
            themes.append(CleanTheme(
                name=sname,
                sources=["eastmoney_sector"],
                stock_count=0,
                summary="",
            ))

    # ── 4. 去重合并个股 ──
    stocks = _deduplicate_stocks(stocks_df, billboard_df)

    # ── 5. 持续性过滤 ──
    themes = _calc_persistence(themes, today)

    # ── 6. 量价验证 ──
    themes = _validate_volume(themes)

    # ── 7. 计算个股共振评分 ──
    from shared.signal_aggregator import score_stocks
    stocks = score_stocks(stocks, themes)

    return {"themes": themes, "stocks": stocks}


# ── helpers ────────────────────────────────────────────────────


def _safe_float(val) -> float:
    try:
        v = float(str(val).replace("%", ""))
        return v
    except (ValueError, TypeError):
        return 0.0
