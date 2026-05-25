"""异动数据源 — 统一数据模型与协议。

新增数据源时：实现 DataSource 协议（提供 name 属性与 fetch 方法），
然后在 shared.api.main 的 SOURCES 字典里注册即可。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ActionItem:
    date: DateType
    source: str
    theme: str
    theme_id: str
    stock_count: int
    summary: str


@runtime_checkable
class DataSource(Protocol):
    name: str

    def fetch(self, target_date: DateType) -> list[ActionItem]: ...
