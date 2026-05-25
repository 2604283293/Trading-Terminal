"""本地 Parquet 数据存储 — 替代 SQLite/FastAPI，UI 直接读取文件。"""
from __future__ import annotations

from datetime import date as DateType
from pathlib import Path

import pandas as pd

# shared/src/shared/local_store.py → parents[3] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_ROOT = _PROJECT_ROOT / "data"

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
    return _actions_path(target_date).exists()
