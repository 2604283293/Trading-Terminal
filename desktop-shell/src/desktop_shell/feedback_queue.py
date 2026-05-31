"""离线反馈队列 — 无网络时存本地，恢复后自动提交。"""
from __future__ import annotations

import json
from pathlib import Path

from desktop_shell.config import get_config_dir


def _queue_path() -> Path:
    return get_config_dir() / "offline_feedback.json"


def enqueue(feedback: dict) -> None:
    """将反馈追加到本地队列。"""
    p = _queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    if p.exists():
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            items = []
    items.append(feedback)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def dequeue_all() -> list[dict]:
    """读取全部队列并清空文件。"""
    p = _queue_path()
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        items = []
    p.write_text("[]", encoding="utf-8")
    return items


def pending_count() -> int:
    p = _queue_path()
    if not p.exists():
        return 0
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
        return len(items)
    except Exception:
        return 0
