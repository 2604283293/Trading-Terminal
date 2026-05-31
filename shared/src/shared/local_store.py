"""本地 Parquet 数据存储 — 替代 SQLite/FastAPI，UI 直接读取文件。"""
from __future__ import annotations

import sys
from datetime import date as DateType
from pathlib import Path

import pandas as pd


def _get_data_root() -> Path:
    """数据根目录：打包后用 %LOCALAPPDATA%，开发环境用项目 data/。"""
    if getattr(sys, "frozen", False):
        import os
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Trading-Terminal" / "data"
    # shared/src/shared/local_store.py → parents[3] = 项目根目录
    return Path(__file__).resolve().parents[3] / "data"


_DATA_ROOT = _get_data_root()

ACTIONS_COLUMNS = ["date", "source", "theme", "theme_id", "stock_count", "summary"]
STOCKS_COLUMNS = [
    "date", "source", "theme",
    "code", "name", "action_type", "summary",
    "last_price", "change_pct", "limit_time", "analysis",
]


def _actions_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "actions" / f"{target_date.isoformat()}.parquet"


def _stocks_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "stocks" / f"{target_date.isoformat()}.parquet"


def save_actions(items: list[dict], target_date: DateType) -> None:
    """保存主题摘要到 Parquet。"""
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (_DATA_ROOT / "actions").mkdir(exist_ok=True)
    df = pd.DataFrame(items, columns=ACTIONS_COLUMNS)
    df.to_parquet(_actions_path(target_date), index=False)


def load_actions(target_date: DateType) -> pd.DataFrame:
    """读取主题摘要。"""
    p = _actions_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=ACTIONS_COLUMNS)
    return pd.read_parquet(p)


def save_stocks(items: list[dict], target_date: DateType) -> None:
    """保存个股明细到 Parquet。"""
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (_DATA_ROOT / "stocks").mkdir(exist_ok=True)
    df = pd.DataFrame(items, columns=STOCKS_COLUMNS)
    df.to_parquet(_stocks_path(target_date), index=False)


def load_stocks(target_date: DateType) -> pd.DataFrame:
    """读取个股明细。"""
    p = _stocks_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=STOCKS_COLUMNS)
    return pd.read_parquet(p)


def has_today_data(target_date: DateType) -> bool:
    """判断是否有任何本地缓存数据（日线/热度/龙虎榜/异动主题/涨跌停/财务）。"""
    return (
        _actions_path(target_date).exists()
        or _daily_dump_path(target_date).exists()
        or _hot_rank_path(target_date).exists()
        or _dragon_tiger_path(target_date).exists()
        or _limit_list_path(target_date).exists()
        or _finance_path(target_date).exists()
    )


# ── 龙虎榜 ────────────────────────────────────────────────────

BILLBOARD_COLUMNS = [
    "date", "code", "name", "price", "change_pct",
    "net_buy", "buy_ratio", "super_large_net", "large_net",
    "medium_net", "small_net", "reason",
]


def _billboard_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "billboard" / f"{target_date.isoformat()}.parquet"


def save_billboard(items: list[dict], target_date: DateType) -> None:
    (_DATA_ROOT / "billboard").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(items, columns=BILLBOARD_COLUMNS)
    df.to_parquet(_billboard_path(target_date), index=False)


def load_billboard(target_date: DateType) -> pd.DataFrame:
    p = _billboard_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=BILLBOARD_COLUMNS)
    return pd.read_parquet(p)


# ── 北向资金 ────────────────────────────────────────────────

NORTHBOUND_COLUMNS = ["date", "net_buy", "buy_amount", "sell_amount", "market"]


def _northbound_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "northbound" / f"{target_date.isoformat()}.parquet"


def save_northbound(items: list[dict], target_date: DateType) -> None:
    (_DATA_ROOT / "northbound").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(items, columns=NORTHBOUND_COLUMNS)
    df.to_parquet(_northbound_path(target_date), index=False)


def load_northbound(target_date: DateType) -> pd.DataFrame:
    p = _northbound_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=NORTHBOUND_COLUMNS)
    return pd.read_parquet(p)


# ── 板块资金流 ──────────────────────────────────────────────

SECTOR_FLOW_COLUMNS = [
    "date", "code", "name", "change_pct",
    "main_net", "main_ratio", "market",
]


def _sector_flow_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "sector_flow" / f"{target_date.isoformat()}.parquet"


def save_sector_flow(items: list[dict], target_date: DateType) -> None:
    (_DATA_ROOT / "sector_flow").mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(items, columns=SECTOR_FLOW_COLUMNS)
    df.to_parquet(_sector_flow_path(target_date), index=False)


def load_sector_flow(target_date: DateType) -> pd.DataFrame:
    p = _sector_flow_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=SECTOR_FLOW_COLUMNS)
    return pd.read_parquet(p)


# ── 全市场日线缓存 (API daily_dump) ──────────────────────────

DAILY_DUMP_COLUMNS = [
    "stock_code", "date", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "volume", "amount",
]


def _daily_dump_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "daily_dump" / f"{target_date.isoformat()}.parquet"


def save_daily_dump(df: pd.DataFrame, target_date: DateType) -> None:
    """保存全市场日线数据到 Parquet 缓存。"""
    (_DATA_ROOT / "daily_dump").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_daily_dump_path(target_date), index=False)


def load_daily_dump(target_date: DateType) -> pd.DataFrame:
    """读取某日的全市场日线缓存。"""
    p = _daily_dump_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=DAILY_DUMP_COLUMNS)
    return pd.read_parquet(p)


def list_cached_dates() -> list[DateType]:
    """列出已缓存的全市场日线日期（按日期升序）。"""
    dump_dir = _DATA_ROOT / "daily_dump"
    if not dump_dir.exists():
        return []
    dates: list[DateType] = []
    for f in dump_dir.iterdir():
        if f.suffix == ".parquet":
            try:
                dates.append(DateType.fromisoformat(f.stem))
            except ValueError:
                pass
    return sorted(dates)


def load_daily_dump_range(
    end_date: DateType,
    min_days: int = 60,
) -> pd.DataFrame:
    """加载截至 end_date 的最近 min_days 个交易日的全市场日线数据。

    用于选股扫描：合并多个单日 Parquet 为一个 DataFrame。
    """
    cached = list_cached_dates()
    eligible = [d for d in cached if d <= end_date]
    selected = eligible[-min_days:] if len(eligible) > min_days else eligible
    frames = []
    for d in selected:
        df = load_daily_dump(d)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=DAILY_DUMP_COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["stock_code", "date"]).reset_index(drop=True)
    return result


# ── 同花顺热度榜 ──────────────────────────────────────────────

HOT_RANK_COLUMNS = ["name", "code", "rank", "pct_change", "hot"]


def _hot_rank_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "hot_rank" / f"{target_date.isoformat()}.parquet"


def save_hot_rank(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "hot_rank").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_hot_rank_path(target_date), index=False)


def load_hot_rank(target_date: DateType) -> pd.DataFrame:
    p = _hot_rank_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=HOT_RANK_COLUMNS)
    return pd.read_parquet(p)


# ── 龙虎榜 (API) ──────────────────────────────────────────────

DRAGON_TIGER_COLUMNS = [
    "trade_date", "stock_code", "name", "close", "pct_change",
    "turnover_rate", "amount", "l_sell", "l_buy", "l_amount",
    "net_amount", "net_rate", "amount_rate", "float_values", "reason",
]


def _dragon_tiger_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "dragon_tiger" / f"{target_date.isoformat()}.parquet"


def save_dragon_tiger(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "dragon_tiger").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_dragon_tiger_path(target_date), index=False)


def load_dragon_tiger(target_date: DateType) -> pd.DataFrame:
    p = _dragon_tiger_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=DRAGON_TIGER_COLUMNS)
    return pd.read_parquet(p)


# ── 龙虎榜席位明细 ──────────────────────────────────────────

DRAGON_TIGER_SEAT_COLUMNS = [
    "trade_date", "stock_code", "org_name",
    "buy_amount", "buy_ratio", "sell_amount", "sell_ratio",
    "net_buy_amount", "direction", "reason",
]


def _dragon_tiger_seat_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "dragon_tiger_seats" / f"{target_date.isoformat()}.parquet"


def save_dragon_tiger_seats(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "dragon_tiger_seats").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_dragon_tiger_seat_path(target_date), index=False)


def load_dragon_tiger_seats(target_date: DateType) -> pd.DataFrame:
    p = _dragon_tiger_seat_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=DRAGON_TIGER_SEAT_COLUMNS)
    return pd.read_parquet(p)


# ── 每日财务指标 (灵启 API: /api/stock/finance) ──────────────

FINANCE_COLUMNS = ["stock_code", "trade_date", "close", "turnover_rate", "pe", "pb"]


def _finance_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "finance" / f"{target_date.isoformat()}.parquet"


def save_finance(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "finance").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_finance_path(target_date), index=False)


def load_finance(target_date: DateType) -> pd.DataFrame:
    p = _finance_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=FINANCE_COLUMNS)
    return pd.read_parquet(p)


# ── 涨跌停列表 (灵启 API: /api/stock/limit_list) ─────────────

LIMIT_LIST_COLUMNS = [
    "trade_date", "stock_code", "name", "industry", "close", "pct_chg",
    "amount", "limit_amount", "float_mv", "total_mv", "turnover_ratio",
    "fd_amount", "first_time", "last_time", "open_times", "up_stat",
    "limit_times", "limit",
]


def _limit_list_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "limit_list" / f"{target_date.isoformat()}.parquet"


def save_limit_list(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "limit_list").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_limit_list_path(target_date), index=False)


def load_limit_list(target_date: DateType) -> pd.DataFrame:
    p = _limit_list_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=LIMIT_LIST_COLUMNS)
    return pd.read_parquet(p)


# ── ETF 日线 (灵启 API: /api/etf/daily) ──────────────────────


def _etf_daily_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "etf_daily" / f"{target_date.isoformat()}.parquet"


def save_etf_daily(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "etf_daily").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_etf_daily_path(target_date), index=False)


def load_etf_daily(target_date: DateType) -> pd.DataFrame:
    p = _etf_daily_path(target_date)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


# ── 集合竞价 (灵启 API: /api/realtime/auction_daily) ──────────

AUCTION_COLUMNS = [
    "stock_code", "stock_name", "update_time", "close", "pre_close",
    "vol", "amount", "turnover_rate", "ask_price", "bid_price",
    "ask_vol", "bid_vol",
]


def _auction_path(target_date: DateType) -> Path:
    return _DATA_ROOT / "auction" / f"{target_date.isoformat()}.parquet"


def save_auction(df: pd.DataFrame, target_date: DateType) -> None:
    (_DATA_ROOT / "auction").mkdir(parents=True, exist_ok=True)
    df.to_parquet(_auction_path(target_date), index=False)


def load_auction(target_date: DateType) -> pd.DataFrame:
    p = _auction_path(target_date)
    if not p.exists():
        return pd.DataFrame(columns=AUCTION_COLUMNS)
    return pd.read_parquet(p)


# ── 交易日历 (灵启 API: /api/basic/calendar) ──────────────────

_CALENDAR_PATH = _DATA_ROOT / "calendar.parquet"


def save_calendar(df: pd.DataFrame) -> None:
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_CALENDAR_PATH, index=False)


def load_calendar() -> pd.DataFrame:
    if not _CALENDAR_PATH.exists():
        return pd.DataFrame(columns=["date", "is_open"])
    return pd.read_parquet(_CALENDAR_PATH)
