from __future__ import annotations

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

API_URL = "http://127.0.0.1:8000"


class NewsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
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
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(self.refresh_btn)
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
        try:
            response = httpx.get(f"{API_URL}/actions", timeout=5.0)
            response.raise_for_status()
            items = response.json()
        except Exception as e:
            self._show_message(
                f"⚠ 无法连接数据服务（{API_URL}）\n\n{type(e).__name__}: {e}\n\n"
                "请先启动数据服务：双击仓库根目录的 run-shared.bat"
            )
            return

        items = [it for it in items if it.get("summary")]
        if not items:
            self._show_message(
                "暂无资讯。先在『板块交易』页点『抓取今日』触发数据拉取。"
            )
            return

        self.title.setText(f"资讯流 · {items[0]['date']} · {len(items)} 条")
        for item in items:
            self._content_layout.addWidget(self._make_entry(item))

    def _make_entry(self, item: dict) -> QFrame:
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
            f" <span style='color:#999;'>·</span> "
            f"<span style='color:#666;'>{item['stock_count']} 只异动</span>"
            f" <span style='color:#999;'>·</span> "
            f"<span style='color:#999; font-size:11px;'>{item['source']} · {item['date']}</span>"
        )
        meta.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(meta)

        body = QLabel(item["summary"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #333; font-size: 14px; line-height: 1.6;")
        layout.addWidget(body)

        return entry

    def _show_message(self, msg: str):
        self._clear_content()
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        self._content_layout.addWidget(label)
