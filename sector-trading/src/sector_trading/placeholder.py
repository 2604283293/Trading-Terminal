"""板块交易 — 阅读本地 Parquet 数据，Selenium 抓取落盘。"""
from __future__ import annotations

from datetime import date as DateType

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from shared.local_store import has_today_data, load_actions, load_stocks, save_actions, save_stocks


class _ScrapeWorker(QObject):
    finished = Signal(dict)

    def __init__(self, target_date: DateType):
        super().__init__()
        self._target = target_date

    def run(self) -> None:
        try:
            from shared.data_sources.jiuyangongshe_selenium import fetch_all

            result = fetch_all(self._target)
            if result["actions"]:
                save_actions(result["actions"], self._target)
            if result["stocks"]:
                save_stocks(result["stocks"], self._target)
            self.finished.emit({
                "ok": True,
                "actions": len(result["actions"]),
                "stocks": len(result["stocks"]),
            })
        except Exception as e:
            self.finished.emit({"ok": False, "error": f"{type(e).__name__}: {e}"})


class SectorTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scrape_thread: QThread | None = None
        self._stocks_df = None
        self._build_ui()
        self._refresh()

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
        self._clear_content()
        today = DateType.today()

        if not has_today_data(today):
            self._show_message(
                "暂无数据。\n\n点击右上角『抓取今日』触发数据拉取（需要安装 Edge 浏览器）。"
            )
            return

        actions_df = load_actions(today)
        try:
            self._stocks_df = load_stocks(today)
        except Exception:
            self._stocks_df = None

        n_actions = len(actions_df)
        n_stocks = 0 if self._stocks_df is None else len(self._stocks_df)
        self.title.setText(f"异动主题 · {today.isoformat()} · {n_actions} 个题材 · {n_stocks} 只个股")

        for _, item in actions_df.iterrows():
            # 过滤该主题下的个股
            theme_stocks = None
            if self._stocks_df is not None and len(self._stocks_df) > 0:
                mask = self._stocks_df["theme"] == item["theme"]
                theme_stocks = self._stocks_df[mask]

            self._content_layout.addWidget(self._make_card(item, theme_stocks))

    def _scrape(self):
        if self._scrape_thread is not None:
            return
        self.scrape_btn.setEnabled(False)
        self.scrape_btn.setText("抓取中…")
        self.status.setText("正在抓取上游数据（Edge 浏览器）…")

        self._scrape_thread = QThread()
        worker = _ScrapeWorker(DateType.today())
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
            self.status.setText(f"抓取完成：{result['actions']} 个题材，{result['stocks']} 只个股")
            self._refresh()
        else:
            self.status.setText("抓取失败")
            self._show_message(
                f"抓取失败：\n\n{result['error']}\n\n"
                "请确认：① Edge 浏览器已安装；② VPN 切到「绕过中国大陆」模式"
            )

    def _make_card(self, item, theme_stocks) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 12px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        # 标题行
        header = QHBoxLayout()
        theme = QLabel(item["theme"])
        theme.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        header.addWidget(theme)
        header.addSpacing(12)
        count = QLabel(f"{item['stock_count']} 只异动")
        count.setStyleSheet("color: #d83a3a; font-size: 13px;")
        header.addWidget(count)
        header.addStretch()
        source = QLabel("@jiuyangongshe")
        source.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(source)
        layout.addLayout(header)

        # 摘要
        if item["summary"]:
            summary = QLabel(item["summary"])
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #444; font-size: 13px;")
            layout.addWidget(summary)

        # 个股列表
        if theme_stocks is not None and len(theme_stocks) > 0:
            stock_box = QVBoxLayout()
            stock_box.setSpacing(2)
            stock_box.setContentsMargins(8, 4, 0, 0)

            header_row = QHBoxLayout()
            for col, w in [("名称", 100), ("代码", 70), ("最新价", 70), ("涨跌幅", 80), ("涨停时间", 70), ("异动", 80)]:
                lbl = QLabel(col)
                lbl.setStyleSheet("color: #999; font-size: 11px;")
                lbl.setFixedWidth(w)
                header_row.addWidget(lbl)
            header_row.addStretch()
            stock_box.addLayout(header_row)

            for _, s in theme_stocks.iterrows():
                row = QHBoxLayout()
                name = QLabel(str(s["name"]))
                name.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
                name.setFixedWidth(100)
                row.addWidget(name)

                code = QLabel(str(s["code"]))
                code.setStyleSheet("font-size: 11px; color: #888;")
                code.setFixedWidth(70)
                row.addWidget(code)

                price = QLabel(str(s["last_price"]))
                price.setStyleSheet("font-size: 12px; color: #333;")
                price.setFixedWidth(70)
                row.addWidget(price)

                pct = str(s["change_pct"])
                pct_color = "#d83a3a" if "+" in pct or "涨停" in pct else ("#2e9f3e" if "-" in pct else "#888")
                change = QLabel(pct)
                change.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {pct_color};")
                change.setFixedWidth(80)
                row.addWidget(change)

                ltime = QLabel(str(s["limit_time"]))
                ltime.setStyleSheet("font-size: 11px; color: #666;")
                ltime.setFixedWidth(70)
                row.addWidget(ltime)

                atype = QLabel(str(s["action_type"]))
                atype.setStyleSheet("font-size: 11px; color: #d83a3a;")
                atype.setFixedWidth(80)
                row.addWidget(atype)

                row.addStretch()
                stock_box.addLayout(row)

            layout.addLayout(stock_box)

        return card

    def _show_message(self, msg: str):
        self._clear_content()
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        self._content_layout.addWidget(label)
