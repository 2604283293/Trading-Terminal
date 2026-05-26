"""统一数据管线 — 定时抓取所有数据源 → Parquet。

用法：
    from shared.data_pipeline import fetch_all
    fetch_all(target_date)  # 抓取当天全部数据
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType
from typing import Callable

from shared.data_sources.eastmoney import (
    BillBoardRow,
    NorthBoundRow,
    SectorFlowRow,
    fetch_billboard,
    fetch_north_bound,
    fetch_sector_flow,
)
from shared.local_store import (
    save_billboard,
    save_northbound,
    save_sector_flow,
)


@dataclass
class PipelineResult:
    billboard: list[BillBoardRow]
    northbound: list[NorthBoundRow]
    sector_flow: list[SectorFlowRow]
    errors: list[str]


def fetch_all(
    target_date: DateType,
    on_progress: Callable[[str], None] | None = None,
) -> PipelineResult:
    """拉取所有东方财富数据源并保存到 Parquet。

    Args:
        target_date: 目标日期
        on_progress: 进度回调 (status_message)
    """
    errors: list[str] = []
    billboard: list[BillBoardRow] = []
    northbound: list[NorthBoundRow] = []
    sector_flow: list[SectorFlowRow] = []

    # ── 龙虎榜 ──
    if on_progress:
        on_progress("正在获取龙虎榜…")
    try:
        billboard = fetch_billboard()
        save_billboard(
            [_billboard_to_dict(r, target_date) for r in billboard],
            target_date,
        )
        if on_progress:
            on_progress(f"龙虎榜: {len(billboard)} 条")
    except Exception as exc:
        msg = f"龙虎榜抓取失败: {exc}"
        errors.append(msg)
        if on_progress:
            on_progress(msg)

    # ── 北向资金 ──
    if on_progress:
        on_progress("正在获取北向资金…")
    try:
        northbound = fetch_north_bound(30)
        # 按日期分组保存
        by_date: dict[str, list[dict]] = {}
        for r in northbound:
            by_date.setdefault(r.date, []).append({
                "date": r.date,
                "net_buy": r.net_buy,
                "buy_amount": r.buy_amount,
                "sell_amount": r.sell_amount,
                "market": "",
            })
        for date_str, items in by_date.items():
            d = DateType.fromisoformat(date_str)
            save_northbound(items, d)
        if on_progress:
            on_progress(f"北向资金: {len(northbound)} 条")
    except Exception as exc:
        msg = f"北向资金抓取失败: {exc}"
        errors.append(msg)
        if on_progress:
            on_progress(msg)

    # ── 板块资金流 ──
    if on_progress:
        on_progress("正在获取板块资金流…")
    try:
        sector_flow = fetch_sector_flow("concept", 30)
        sector_flow.extend(fetch_sector_flow("industry", 30))
        save_sector_flow(
            [_sector_flow_to_dict(r, target_date) for r in sector_flow],
            target_date,
        )
        if on_progress:
            on_progress(f"板块资金流: {len(sector_flow)} 条")
    except Exception as exc:
        msg = f"板块资金流抓取失败: {exc}"
        errors.append(msg)
        if on_progress:
            on_progress(msg)

    return PipelineResult(
        billboard=billboard,
        northbound=northbound,
        sector_flow=sector_flow,
        errors=errors,
    )


# ── helpers ────────────────────────────────────────────────────

def _billboard_to_dict(r: BillBoardRow, d: DateType) -> dict:
    return {
        "date": d.isoformat(),
        "code": r.code,
        "name": r.name,
        "price": r.price,
        "change_pct": r.change_pct,
        "net_buy": r.net_buy,
        "buy_ratio": r.buy_ratio,
        "super_large_net": r.super_large_net,
        "large_net": r.large_net,
        "medium_net": r.medium_net,
        "small_net": r.small_net,
        "reason": r.reason,
    }


def _sector_flow_to_dict(r: SectorFlowRow, d: DateType) -> dict:
    return {
        "date": d.isoformat(),
        "code": r.code,
        "name": r.name,
        "change_pct": r.change_pct,
        "main_net": r.main_net,
        "main_ratio": r.main_ratio,
        "market": r.market,
    }
