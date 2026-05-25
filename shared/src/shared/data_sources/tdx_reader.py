"""TDX 本地 K 线文件读取器。

支持 .day（日线）、.lc5（5 分钟）、.lc1（1 分钟）。

日线格式（32 字节/条）：
  uint32 date(YYYYMMDD), uint32 open(*100), uint32 high(*100),
  uint32 low(*100), uint32 close(*100), float32 amount, uint32 volume, uint32 reserved

分钟线格式（32 字节/条）：
  uint16 day_number, uint16 minute_of_day, float32 open, float32 high,
  float32 low, float32 close, float32 amount, uint32 volume, uint32 reserved
  day_number 为 1900-01-01 起的天数
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date as DateType, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

_MINUTE_EPOCH = DateType(1900, 1, 1)

# vipdoc 解压后的根目录
# shared/src/shared/data_sources/tdx_reader.py → parents[4] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_VIPDOC_ROOT = _PROJECT_ROOT / "vipdoc"

_PERIOD_EXT = {"daily": "lday", "5min": "minline", "1min": "minline"}
_PERIOD_SUFFIX = {"daily": ".day", "5min": ".lc5", "1min": ".lc1"}


@dataclass
class KlineRecord:
    date: DateType  # 仅日线有效
    time: Optional[str]  # 分钟线的时间 HH:MM；日线为 None
    open: float
    high: float
    low: float
    close: float
    amount: float
    volume: int


def _resolve_path(code: str, period: str = "daily") -> Path:
    """将股票代码解析为 vipdoc 下的 .day/.lc5/.lc1 路径。

    code 形如 "sh600519"、"sz000001"、"bj430047"。
    """
    code = code.lower()
    if code.startswith("sh"):
        market = "sh"
    elif code.startswith("sz"):
        market = "sz"
    elif code.startswith("bj"):
        market = "bj"
    else:
        raise ValueError(f"无法识别市场: {code!r}")

    numeric = code[2:]
    ext_dir = _PERIOD_EXT[period]
    suffix = _PERIOD_SUFFIX[period]
    return _VIPDOC_ROOT / market / ext_dir / f"{code}{suffix}"


def _parse_daily_records(data: bytes) -> list[dict]:
    """解析日线 32 字节记录。"""
    records: list[dict] = []
    n = len(data) // 32
    for i in range(n):
        rec = data[i * 32 : (i + 1) * 32]
        date_int, op, hi, lo, cl, amt, vol, _res = struct.unpack("=I I I I I f I I", rec)
        try:
            d = datetime.strptime(str(date_int), "%Y%m%d").date()
        except ValueError:
            continue
        records.append(
            {
                "date": d,
                "time": None,
                "open": op / 100.0,
                "high": hi / 100.0,
                "low": lo / 100.0,
                "close": cl / 100.0,
                "amount": amt,
                "volume": int(vol),
            }
        )
    return records


def _parse_minute_records(data: bytes) -> list[dict]:
    """解析分钟线 32 字节记录。

    格式: uint16 day_number, uint16 minute, float OHLC, float amount, uint32 volume, uint32 reserved
    """
    records: list[dict] = []
    n = len(data) // 32
    for i in range(n):
        rec = data[i * 32 : (i + 1) * 32]
        day_num, minute = struct.unpack("=H H", rec[0:4])
        op, hi, lo, cl, amt = struct.unpack("=5f", rec[4:24])
        vol = struct.unpack("=I", rec[24:28])[0]
        try:
            d = _MINUTE_EPOCH + timedelta(days=day_num)
        except Exception:
            continue
        hh = minute // 60
        mm = minute % 60
        records.append(
            {
                "date": d,
                "time": f"{hh:02d}:{mm:02d}",
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "amount": amt,
                "volume": int(vol),
            }
        )
    return records


def read_kline(code: str, period: str = "daily") -> pd.DataFrame:
    """读取指定股票 + 周期的 K 线数据，返回 DataFrame。

    code: "sh600519", "sz000001" 等
    period: "daily" | "5min" | "1min"
    """
    path = _resolve_path(code, period)
    suffix = _PERIOD_SUFFIX[period]

    if not path.exists():
        raise FileNotFoundError(f"TDX 数据文件不存在: {path}")

    data = path.read_bytes()

    if suffix == ".day":
        records = _parse_daily_records(data)
    else:
        records = _parse_minute_records(data)

    if not records:
        return pd.DataFrame(columns=["date", "time", "open", "high", "low", "close", "amount", "volume"])

    df = pd.DataFrame(records)
    df = df.sort_values("date" if suffix == ".day" else ["date", "time"]).reset_index(drop=True)
    return df


def list_codes(market: str = "all") -> list[str]:
    """列出 vipdoc 中所有可用的股票代码。market: "sh" | "sz" | "bj" | "all"."""
    codes: list[str] = []
    markets = ["sh", "sz", "bj"] if market == "all" else [market]
    for mkt in markets:
        lday_dir = _VIPDOC_ROOT / mkt / "lday"
        if not lday_dir.exists():
            continue
        for f in lday_dir.iterdir():
            if f.suffix == ".day":
                codes.append(f.stem)
    return sorted(codes)
