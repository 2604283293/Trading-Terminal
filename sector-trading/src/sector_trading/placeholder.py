from __future__ import annotations

import httpx
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
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


class _ScrapeWorker(QObject):
    finished = Signal(dict)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            response = httpx.post(self._url, timeout=120.0)
            response.raise_for_status()
            self.finished.emit({"ok": True, "data": response.json()})
        except Exception as e:
            self.finished.emit({"ok": False, "error": f"{type(e).__name__}: {e}"})


class SectorTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scrape_thread: QThread | None = None
        self._build_ui()
        QTimer.singleShot(100, self._refresh)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.title = QLabel("异动主题")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        toolbar.addWidget(self.title)
        toolbar.addStretch()

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888; font-size: 12px;")
        toolbar.addWidget(self.status)

        self.scrape_btn = QPushButton("抓取今日")
        self.scrape_btn.clicked.connect(self._scrape)
        toolbar.addWidget(self.scrape_btn)

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
        self._content_layout.setSpacing(8)
        scroll.setWidget(self._content)
        layout.addWidget(scroll, stretch=1)

    def _clear_content(self):
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _refresh(self):
        print("[sector] _refresh called")
        self._clear_content()
        try:
            print("[sector] httpx.get starting...")
            response = httpx.get(f"{API_URL}/actions", timeout=5.0)
            print("[sector] httpx.get returned")
            response.raise_for_status()
            items = response.json()
        except Exception as e:
            self._show_message(
                f"⚠ 无法连接数据服务（{API_URL}）\n\n{type(e).__name__}: {e}\n\n"
                "请先启动数据服务：双击仓库根目录的 run-shared.bat"
            )
            return

        if not items:
            self._show_message(
                "暂无数据。\n\n点击右上角『抓取今日』触发首次抓取，再点『刷新』查看。"
            )
            return

        self.title.setText(f"异动主题 · {items[0]['date']} · {len(items)} 个题材")
        for item in items:
            self._content_layout.addWidget(self._make_card(item))

    def _scrape(self):
        if self._scrape_thread is not None:
            return
        self.scrape_btn.setEnabled(False)
        self.scrape_btn.setText("抓取中…")
        self.status.setText("正在抓取上游数据…")

        self._scrape_thread = QThread()
        worker = _ScrapeWorker(f"{API_URL}/actions/scrape")
        worker.moveToThread(self._scrape_thread)
        self._scrape_thread.started.connect(worker.run)
        worker.finished.connect(self._on_scrape_done)
        worker.finished.connect(self._scrape_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._scrape_thread.finished.connect(self._scrape_thread.deleteLater)
        self._scrape_worker = worker
        self._scrape_thread.start()

    def _on_scrape_done(self, result: dict):
        self.scrape_btn.setEnabled(True)
        self.scrape_btn.setText("抓取今日")
        self._scrape_thread = None
        self._scrape_worker = None

        if result["ok"]:
            data = result["data"]
            errs = data.get("errors") or []
            if errs:
                self.status.setText(f"⚠ 抓取部分失败：{len(errs)} 个源出错")
            else:
                self.status.setText(f"✓ 抓取完成：{data['scraped']} 条")
            self._refresh()
        else:
            self.status.setText("⚠ 抓取失败")
            self._show_message(
                f"⚠ 抓取失败：\n\n{result['error']}\n\n"
                "可能原因：① VPN 走海外路由导致访问韭研公社很慢；"
                "建议切到「绕过中国大陆」规则模式或临时关闭 VPN。"
            )

    def _make_card(self, item: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 12px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        header = QHBoxLayout()
        theme = QLabel(item["theme"])
        theme.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        header.addWidget(theme)
        header.addSpacing(12)
        count = QLabel(f"{item['stock_count']} 只异动")
        count.setStyleSheet("color: #d83a3a; font-size: 13px;")
        header.addWidget(count)
        header.addStretch()
        source = QLabel(f"@{item['source']}")
        source.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(source)
        layout.addLayout(header)

        if item["summary"]:
            summary = QLabel(item["summary"])
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #444; font-size: 13px;")
            layout.addWidget(summary)

        return card

    def _show_message(self, msg: str):
        self._clear_content()
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        self._content_layout.addWidget(label)
