"""东方财富数据源 — 龙虎榜 / 北向资金 / 板块资金流。

全部通过公开 HTTP API 获取，无需认证。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as DateType, datetime, timedelta
from typing import Any

import httpx

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_HEADERS = {"Referer": "https://data.eastmoney.com/", "User-Agent": _UA}

# East Money 内部标识
_SH_CODES = {"sh", "SH", "Sh"}  # 上海市场
_SZ_CODES = {"sz", "SZ", "Sz"}  # 深圳市场


def _code_with_market(eastmoney_code: str) -> str:
    """东方财富代码（如 600519.SH）→ 本地代码（sh600519）。"""
    if eastmoney_code.endswith(".SH"):
        return f"sh{eastmoney_code[:-3]}"
    elif eastmoney_code.endswith(".SZ"):
        return f"sz{eastmoney_code[:-3]}"
    elif eastmoney_code.endswith(".BJ"):
        return f"bj{eastmoney_code[:-3]}"
    return eastmoney_code


# ── 龙虎榜 ─────────────────────────────────────────────────────


@dataclass
class BillBoardRow:
    code: str          # 本地代码 sh600519
    name: str          # 股票名称
    price: float       # 最新价
    change_pct: float  # 涨跌幅%
    net_buy: float     # 主力净买入（元）
    buy_ratio: float   # 主力买入占比%
    super_large_net: float  # 超大单净买入
    large_net: float        # 大单净买入
    medium_net: float       # 中单净买入
    small_net: float        # 小单净买入
    reason: str        # 上榜原因


def fetch_billboard(target_date: DateType | None = None) -> list[BillBoardRow]:
    """获取当日龙虎榜数据。"""
    results: list[BillBoardRow] = []
    page = 1
    client = httpx.Client(timeout=httpx.Timeout(30))

    while True:
        params = {
            "fid": "f184",
            "po": str(page),
            "pz": "50",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205",
            "np": "1",
            "fltt": "2",
            "invt": "2",
        }
        resp = client.get(
            "https://push2.eastmoney.com/api/qt/clt/get",
            params=params,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

        if data is None or data.get("data") is None:
            break

        items = data["data"].get("diff", [])
        if not items:
            break

        for item in items:
            results.append(BillBoardRow(
                code=_code_with_market(item.get("f12", "")),
                name=item.get("f14", ""),
                price=float(item.get("f2", 0) or 0),
                change_pct=float(item.get("f3", 0) or 0),
                net_buy=float(item.get("f62", 0) or 0),
                buy_ratio=float(item.get("f184", 0) or 0),
                super_large_net=float(item.get("f66", 0) or 0),
                large_net=float(item.get("f72", 0) or 0),
                medium_net=float(item.get("f78", 0) or 0),
                small_net=float(item.get("f84", 0) or 0),
                reason=item.get("f204", ""),
            ))

        total = data["data"].get("total", 0)
        if page * 50 >= total:
            break
        page += 1

    client.close()
    return results


# ── 北向资金 ───────────────────────────────────────────────────


@dataclass
class NorthBoundRow:
    date: str         # YYYY-MM-DD
    net_buy: float    # 当日净买入（元）
    buy_amount: float # 买入成交额
    sell_amount: float# 卖出成交额


def fetch_north_bound(days: int = 30) -> list[NorthBoundRow]:
    """获取最近 N 日北向资金汇总（沪股通 + 深股通合计）。"""
    results: list[NorthBoundRow] = []
    client = httpx.Client(timeout=httpx.Timeout(30))

    for mkt_id, name in [("1", "沪股通"), ("3", "深股通")]:
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55,f56",
            "klt": "101",       # 日线
            "lmt": str(days),
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        resp = client.get(
            f"https://push2.eastmoney.com/api/qt/kamt.kline/get?market={mkt_id}",
            params=params,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

        if data is None or data.get("data") is None:
            continue

        klines = data["data"].get("klines", [])
        for line in klines:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            results.append(NorthBoundRow(
                date=parts[0],
                net_buy=float(parts[1]) if parts[1] != "-" else 0.0,
                buy_amount=float(parts[2]) if parts[2] != "-" else 0.0,
                sell_amount=float(parts[3]) if parts[3] != "-" else 0.0,
            ))

    client.close()
    return results


# ── 板块资金流 ─────────────────────────────────────────────────


@dataclass
class SectorFlowRow:
    code: str          # 板块代码
    name: str          # 板块名称
    change_pct: float  # 涨跌幅%
    main_net: float    # 主力净流入（元）
    main_ratio: float  # 主力净流入占比%
    market: str        # "industry" | "concept"


def fetch_sector_flow(sector_type: str = "concept", top_n: int = 30) -> list[SectorFlowRow]:
    """获取板块资金流排名。

    Args:
        sector_type: "industry" (行业) | "concept" (概念)
        top_n: 返回前 N 名
    """
    market_map = {"industry": "m:90+t1", "concept": "m:90+t2"}
    fs = market_map.get(sector_type, "m:90+t2")

    client = httpx.Client(timeout=httpx.Timeout(30))
    params = {
        "spt": "1",
        "fltt": "2",
        "invt": "2",
        "fields": "f12,f14,f2,f3,f62,f184,f66,f72,f78,f84",
        "fid": "f62",  # 按主力净流入排序
        "fs": fs,
        "pn": "1",
        "pz": str(top_n),
    }
    resp = client.get(
        "https://push2.eastmoney.com/api/qt/slist/get",
        params=params,
        headers=_HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    client.close()

    results: list[SectorFlowRow] = []
    if data is None or data.get("data") is None:
        return results

    for item in data["data"].get("diff", []):
        results.append(SectorFlowRow(
            code=item.get("f12", ""),
            name=item.get("f14", ""),
            change_pct=float(item.get("f3", 0) or 0),
            main_net=float(item.get("f62", 0) or 0),
            main_ratio=float(item.get("f184", 0) or 0),
            market=sector_type,
        ))

    return results


def fetch_all_sector_flow(top_n: int = 30) -> list[SectorFlowRow]:
    """获取行业 + 概念板块资金流。"""
    results: list[SectorFlowRow] = []
    results.extend(fetch_sector_flow("industry", top_n))
    results.extend(fetch_sector_flow("concept", top_n))
    return results
