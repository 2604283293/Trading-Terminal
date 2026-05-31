"""统一数据管线 — 定时抓取所有数据源 → Parquet。

用法：
    from shared.data_pipeline import fetch_all, fetch_api_data
    fetch_all(target_date)         # 抓取东方财富数据
    fetch_api_data(target_date)    # 抓取灵启数据 API 数据
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
from shared.lingqi_client import (
    fetch_daily_dump,
    fetch_dragon_tiger,
    fetch_hot_rank,
    fetch_top_list,
    fetch_stock_finance,
    fetch_limit_list,
    fetch_etf_daily,
    fetch_auction_daily,
    fetch_trade_calendar,
)
from shared.local_store import (
    save_billboard,
    save_daily_dump,
    save_dragon_tiger,
    save_dragon_tiger_seats,
    save_hot_rank,
    save_northbound,
    save_sector_flow,
    save_finance,
    save_limit_list,
    save_etf_daily,
    save_auction,
    save_calendar,
    load_calendar,
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


# ── 灵启数据 API 管线 ──────────────────────────────────────────


@dataclass
class ApiDataResult:
    daily_dump_rows: int
    hot_rank_rows: int
    dragon_tiger_rows: int
    dragon_tiger_seats_rows: int
    finance_rows: int
    limit_list_rows: int
    etf_daily_rows: int
    auction_rows: int
    calendar_rows: int
    errors: list[str]


def fetch_api_data(
    target_date: DateType,
    on_progress: Callable[[str], None] | None = None,
) -> ApiDataResult:
    """从灵启数据 API 抓取全市场日线、同花顺热度、龙虎榜，缓存为 Parquet。

    注意：daily_dump 接口每日期每天限制 10 次调用。
    """
    errors: list[str] = []
    daily_rows = 0
    hot_rows = 0
    dt_rows = 0
    finance_rows = 0
    limit_rows = 0
    etf_rows = 0
    auction_rows = 0
    calendar_rows = 0

    # ── 全市场日线 ──
    def _report(msg: str):
        if on_progress:
            on_progress(msg)

    _report("【全市场日线】开始下载…")
    try:
        df = fetch_daily_dump(target_date, on_progress=on_progress)
        if not df.empty:
            _report("正在保存到本地缓存…")
            save_daily_dump(df, target_date)
            daily_rows = len(df)
            _report(f"全市场日线: {daily_rows} 条 (已缓存到 data/daily_dump/)")
    except Exception as exc:
        msg = f"全市场日线下载失败: {exc}"
        errors.append(msg)
        _report(msg)

    # ── 同花顺热度榜 ──
    _report("正在获取同花顺热度榜…")
    hot_frames = []
    for market in ["热股", "行业板块", "概念板块"]:
        try:
            df = fetch_hot_rank(market=market, trade_date=target_date)
            if not df.empty:
                df["market"] = market
                hot_frames.append(df)
                hot_rows += len(df)
        except Exception as exc:
            msg = f"同花顺热度({market})获取失败: {exc}"
            errors.append(msg)
    if hot_frames:
        import pandas as pd
        merged = pd.concat(hot_frames, ignore_index=True)
        save_hot_rank(merged, target_date)
    _report(f"同花顺热度: {hot_rows} 条")

    # ── 龙虎榜 (股票级) ──
    top_list_codes: list[str] = []
    if on_progress:
        on_progress("正在获取龙虎榜…")
    try:
        df = fetch_top_list(target_date)
        if not df.empty:
            save_dragon_tiger(df, target_date)
            dt_rows = len(df)
            top_list_codes = df["stock_code"].unique().tolist()
            if on_progress:
                on_progress(f"龙虎榜: {dt_rows} 条")
    except Exception as exc:
        msg = f"龙虎榜获取失败: {exc}"
        errors.append(msg)
        if on_progress:
            on_progress(msg)

    # ── 龙虎榜席位明细 (逐只股票) ──
    dt_seats_rows = 0
    if top_list_codes:
        if on_progress:
            on_progress(f"正在获取 {len(top_list_codes)} 只龙虎榜股票席位明细…")
        seat_frames = []
        for i, code in enumerate(top_list_codes):
            try:
                seat_df = fetch_dragon_tiger(date=target_date, stock_code=code)
                if not seat_df.empty:
                    seat_frames.append(seat_df)
            except Exception as exc:
                msg = f"席位明细({code})获取失败: {exc}"
                errors.append(msg)
            if on_progress and (i + 1) % 20 == 0:
                on_progress(f"席位明细: {i + 1}/{len(top_list_codes)}")
        if seat_frames:
            import pandas as pd
            all_seats = pd.concat(seat_frames, ignore_index=True)
            save_dragon_tiger_seats(all_seats, target_date)
            dt_seats_rows = len(all_seats)
        if on_progress:
            on_progress(f"席位明细: {dt_seats_rows} 条 (来自 {len(seat_frames)} 只有效数据)")

    # ── 涨跌停列表 ──
    _report("正在获取涨跌停列表…")
    try:
        df = fetch_limit_list(start=target_date, end=target_date)
        if not df.empty:
            save_limit_list(df, target_date)
            limit_rows = len(df)
            _report(f"涨跌停列表: {limit_rows} 条")
        else:
            _report("涨跌停列表: 无数据")
    except Exception as exc:
        msg = f"涨跌停列表获取失败: {exc}"
        errors.append(msg)
        _report(msg)

    # ── 每日财务指标 ──
    _report("正在获取全市场财务指标 (PE/PB/换手率)…")
    try:
        df = fetch_stock_finance(start=target_date, end=target_date)
        if not df.empty:
            save_finance(df, target_date)
            finance_rows = len(df)
            _report(f"财务指标: {finance_rows} 条")
        else:
            _report("财务指标: 无数据")
    except Exception as exc:
        msg = f"财务指标获取失败: {exc}"
        errors.append(msg)
        _report(msg)

    # ── ETF 日线 ──
    _report("正在获取 ETF 日线数据…")
    try:
        df = fetch_etf_daily(start=target_date, end=target_date)
        if not df.empty:
            save_etf_daily(df, target_date)
            etf_rows = len(df)
            _report(f"ETF 日线: {etf_rows} 条")
        else:
            _report("ETF 日线: 无数据")
    except Exception as exc:
        msg = f"ETF 日线获取失败: {exc}"
        errors.append(msg)
        _report(msg)

    # ── 集合竞价 ──（仅当天有数据）
    if target_date == DateType.today():
        _report("正在获取集合竞价数据…")
        try:
            df = fetch_auction_daily(target_date=target_date)
            if not df.empty:
                save_auction(df, target_date)
                auction_rows = len(df)
                _report(f"集合竞价: {auction_rows} 条")
            else:
                _report("集合竞价: 无数据（可能尚未开始）")
        except Exception as exc:
            msg = f"集合竞价获取失败: {exc}"
            errors.append(msg)
            _report(msg)
    else:
        _report("集合竞价: 跳过（仅当天可获取）")

    # ── 交易日历 ──（一次性拉取一年，首次或每月刷新）
    _report("正在更新交易日历…")
    try:
        existing = load_calendar()
        if existing.empty:
            # 首次拉取：当前年份 ±1 年
            year = target_date.year
            cal = fetch_trade_calendar(
                DateType(year - 1, 1, 1),
                DateType(year + 1, 12, 31),
            )
            if not cal.empty:
                save_calendar(cal)
                calendar_rows = len(cal)
                _report(f"交易日历: {calendar_rows} 天")
        else:
            _report("交易日历: 已缓存")
    except Exception as exc:
        msg = f"交易日历获取失败: {exc}"
        errors.append(msg)
        _report(msg)

    return ApiDataResult(
        daily_dump_rows=daily_rows,
        hot_rank_rows=hot_rows,
        dragon_tiger_rows=dt_rows,
        dragon_tiger_seats_rows=dt_seats_rows,
        finance_rows=finance_rows,
        limit_list_rows=limit_rows,
        etf_daily_rows=etf_rows,
        auction_rows=auction_rows,
        calendar_rows=calendar_rows,
        errors=errors,
    )
