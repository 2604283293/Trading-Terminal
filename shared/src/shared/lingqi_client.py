"""灵启数据 API 客户端 — 封装 REST 接口调用。

Base URL: https://data.diemeng.chat/api
Auth: Header apiKey
"""

from __future__ import annotations

import gzip
from datetime import date as DateType
from typing import Any, Callable

import httpx
import pandas as pd

BASE_URL = "https://data.diemeng.chat"
API_KEY = "ad8b24b8339b57e4a24291a302523d625725f6c04bf6cd82eb"

_DEFAULT_TIMEOUT = httpx.Timeout(60.0, read=120.0)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"apiKey": API_KEY},
        timeout=_DEFAULT_TIMEOUT,
    )


def _post(path: str, json: dict | None = None) -> dict[str, Any]:
    """POST 请求，返回 JSON 响应体。"""
    with _client() as cli:
        r = cli.post(path, json=json)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 200:
            raise RuntimeError(f"API error: {data.get('msg', 'unknown')}")
        return data


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    """GET 请求，返回 JSON 响应体。"""
    with _client() as cli:
        r = cli.get(path, params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 200:
            raise RuntimeError(f"API error: {data.get('msg', 'unknown')}")
        return data


# ── 日线数据 ──────────────────────────────────────────────────────


def fetch_daily_dump(
    date: DateType,
    on_progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """下载全市场日线数据（单日全部股票）。

    对应 POST /api/stock/daily_dump?level=daily
    返回所有股票在指定日期的日线行情，含 open/high/low/close/vol/amount 等。
    接口返回 GZIP 压缩 JSON，每日每日期限制调用 10 次。
    """
    def _report(msg: str):
        if on_progress:
            on_progress(msg)

    _report("正在连接 API 服务器…")
    with _client() as cli:
        _report(f"正在下载 {date.isoformat()} 全市场日线数据 (预计 10-30 秒)…")
        r = cli.post(
            "/api/stock/daily_dump",
            json={"date": date.isoformat(), "level": "daily"},
            timeout=httpx.Timeout(120.0, read=300.0),
        )
        r.raise_for_status()
        content_len = len(r.content)
        _report(f"下载完成 ({content_len / 1024 / 1024:.1f} MB), 正在解析…")

        # httpx 自动解压 gzip，但部分情况下仍可能是原始 gzip 数据
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data: dict = __import__("json").loads(raw)
        if data.get("code") != 200:
            raise RuntimeError(f"API error: {data.get('msg', 'unknown')}")

    records = data["data"]
    if not records:
        _report("该日期无交易数据")
        return pd.DataFrame(columns=[
            "stock_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount",
        ])

    _report(f"解析完成, 共 {len(records)} 条日线数据, 正在整理…")
    df = pd.DataFrame(records)
    if "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    if "trade_date" in df.columns:
        df["date"] = pd.to_datetime(df["trade_date"], format="%Y-%m-%d", errors="coerce")
    _report(f"全市场日线数据就绪: {len(df)} 只股票")
    return df


def fetch_stock_daily_batch(
    codes: list[str],
    start: DateType,
    end: DateType,
) -> pd.DataFrame:
    """批量获取多只股票日K线（最多 100 只）。

    对应 POST /api/stock/daily
    """
    if not codes:
        return pd.DataFrame()
    if len(codes) > 100:
        raise ValueError("最多支持 100 只股票同时查询")

    data = _post("/api/stock/daily", json={
        "stock_code": codes,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    records = data.get("data", {}).get("list", [])
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    if "trade_date" in df.columns:
        df["date"] = pd.to_datetime(df["trade_date"], format="%Y-%m-%d", errors="coerce")
    return df


# ── 同花顺热度榜 ──────────────────────────────────────────────────


def fetch_hot_rank(
    market: str = "热股",
    trade_date: DateType | None = None,
) -> pd.DataFrame:
    """获取同花顺热度榜。

    对应 GET/POST /api/ths/hot

    Args:
        market: 热股, ETF, 可转债, 行业板块, 概念板块, 期货
        trade_date: 交易日，None 为最新
    """
    params: dict[str, str] = {"market": market}
    if trade_date is not None:
        params["trade_date"] = trade_date.isoformat()

    with _client() as cli:
        r = cli.get("/api/ths/hot", params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 200:
            raise RuntimeError(f"API error: {data.get('msg', 'unknown')}")

    records = data.get("data", {}).get("list", [])
    if not records:
        return pd.DataFrame(columns=["name", "code", "rank", "pct_change", "hot"])
    return pd.DataFrame(records)


# ── 龙虎榜 ────────────────────────────────────────────────────────


def fetch_dragon_tiger(
    date: DateType | None = None,
    stock_code: str | None = None,
) -> pd.DataFrame:
    """获取龙虎榜机构明细。

    对应 POST /api/stock/dragon_tiger
    """
    body: dict[str, str] = {}
    if date is not None:
        body["date"] = date.isoformat()
    if stock_code is not None:
        body["stock_code"] = stock_code

    data = _post("/api/stock/dragon_tiger", json=body)
    records = data.get("data", [])
    if isinstance(records, dict):
        records = records.get("list", [])
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def fetch_top_list(trade_date: DateType) -> pd.DataFrame:
    """获取龙虎榜每日明细。

    对应 POST /api/stock/top_list
    """
    data = _post("/api/stock/top_list", json={"trade_date": trade_date.isoformat()})
    records = data.get("data", [])
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


# ── 股票列表 ──────────────────────────────────────────────────────


def fetch_stock_list() -> pd.DataFrame:
    """获取全市场股票列表。

    对应 GET /api/stock/list
    """
    data = _get("/api/stock/list")
    records = data.get("data", {}).get("list", [])
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)
