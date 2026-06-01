"""资讯流 — 阅读本地 Parquet 数据，展示异动主题资讯。"""
from __future__ import annotations

from datetime import date as DateType

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from shared.local_store import has_today_data, load_actions


class NewsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._current_date: DateType = DateType.today()
        self._build_ui()
        self._refresh()

    def set_date(self, date: DateType) -> None:
        """切换查看日期（由主窗口日期选择器调用）。"""
        self._current_date = date
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.title = QLabel("资讯流")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        toolbar.addWidget(self.title)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setSpacing(0)
        scroll.setWidget(self._content)
        layout.addWidget(scroll, stretch=1)

    def _clear_content(self):
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _refresh(self):
        self._clear_content()
        today = self._current_date

        if not has_today_data(today):
            self._show_message(
                "暂无资讯。\n\n请先在『板块交易』页点击『抓取今日』触发数据拉取。"
            )
            return

        df = load_actions(today)
        items = [row for _, row in df.iterrows() if row["summary"]]
        if not items:
            self._show_message("暂无资讯。先点击板块交易页『抓取今日』触发数据拉取。")
            return

        self.title.setText(f"资讯流 · {today.isoformat()} · {len(items)} 条")
        for item in items:
            self._content_layout.addWidget(self._make_entry(item))

    def _make_entry(self, item) -> QFrame:
        entry = QFrame()
        entry.setStyleSheet(
            "QFrame { background: transparent; border-bottom: 1px solid #eee; "
            "padding: 14px 4px; }"
        )
        layout = QVBoxLayout(entry)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 10, 4, 14)

        meta = QLabel(
            f"<span style='color:#d83a3a; font-weight:bold;'>{item['theme']}</span>"
            f" <span style='color:#999;'>-</span> "
            f"<span style='color:#666;'>{item['stock_count']} 只异动</span>"
            f" <span style='color:#999;'>-</span> "
            f"<span style='color:#999; font-size:11px;'>jiuyangongshe - {item['date']}</span>"
        )
        meta.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(meta)

        body = QLabel(item["summary"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #ccc; font-size: 14px; line-height: 1.6;")
        layout.addWidget(body)

        return entry

    def _show_message(self, msg: str):
        self._clear_content()
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        self._content_layout.addWidget(label)
