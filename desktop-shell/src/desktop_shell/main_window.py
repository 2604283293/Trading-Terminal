"""Trading Terminal 主窗口。"""
from __future__ import annotations

from datetime import date as DateType

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from graphical_trading import GraphicalTradingWidget
from news import NewsWidget
from sector_trading import SectorTradingWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Terminal")
        self.resize(1280, 800)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 日期导航条 ──
        nav = QWidget()
        nav.setStyleSheet("QWidget { background: #f5f5f5; border-bottom: 1px solid #e0e0e0; }")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 6, 12, 6)
        nav_layout.setSpacing(6)

        prev_btn = QPushButton("<")
        prev_btn.setFixedWidth(28)
        prev_btn.setStyleSheet(
            "QPushButton { border: 1px solid #ccc; border-radius: 3px; background: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        nav_layout.addWidget(prev_btn)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setMaximumDate(DateType.today())
        self._date_edit.setDate(DateType.today())
        self._date_edit.setStyleSheet(
            "QDateEdit { border: 1px solid #ccc; border-radius: 3px; padding: 3px 6px; "
            "background: #fff; font-size: 13px; color: #333; }"
            "QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; "
            "width: 20px; border-left: 1px solid #e0e0e0; }"
            "QDateEdit::down-arrow { image: none; border-left: 4px solid transparent; "
            "border-right: 4px solid transparent; border-top: 5px solid #888; "
            "margin-right: 4px; }"
        )
        cal = self._date_edit.calendarWidget()
        cal.setStyleSheet(
            "QCalendarWidget { background: #fff; }"
            "QCalendarWidget QToolButton { color: #333; background: #f0f0f0; "
            "border: 1px solid #ddd; border-radius: 3px; padding: 4px 8px; font-weight: bold; }"
            "QCalendarWidget QToolButton:hover { background: #e0e0e0; }"
            "QCalendarWidget QSpinBox { border: 1px solid #ccc; border-radius: 2px; "
            "padding: 2px 4px; color: #333; background: #fff; }"
            "QCalendarWidget QTableView { color: #333; background: #fff; "
            "selection-background-color: #d83a3a; selection-color: white; font-size: 12px; "
            "outline: none; }"
        )
        nav_layout.addWidget(self._date_edit)

        next_btn = QPushButton(">")
        next_btn.setFixedWidth(28)
        next_btn.setStyleSheet(
            "QPushButton { border: 1px solid #ccc; border-radius: 3px; background: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        nav_layout.addWidget(next_btn)

        today_btn = QPushButton("今天")
        today_btn.setStyleSheet(
            "QPushButton { border: 1px solid #d83a3a; border-radius: 3px; color: #d83a3a; "
            "background: #fff; padding: 3px 10px; font-weight: bold; }"
            "QPushButton:hover { background: #ffe0e0; }"
        )
        nav_layout.addWidget(today_btn)

        nav_layout.addStretch()
        layout.addWidget(nav)

        # ── 标签页 ──
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._graphical = GraphicalTradingWidget()
        self._sector = SectorTradingWidget()
        self._news = NewsWidget()

        self._tabs.addTab(self._graphical, "图形交易")
        self._tabs.addTab(self._sector, "板块交易")
        self._tabs.addTab(self._news, "资讯")
        layout.addWidget(self._tabs, stretch=1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪 — 数据来源：本地 Parquet 文件")

        # ── 日期变更 → 通知各 tab ──
        def _on_date_changed():
            d = self._date_edit.date().toPython()
            self._graphical.set_date(d)
            self._sector.set_date(d)
            self._news.set_date(d)
            is_today = (d == DateType.today())
            self.statusBar().showMessage(
                f"查看日期: {d.isoformat()}" if not is_today
                else "就绪 — 数据来源：本地 Parquet 文件"
            )

        self._date_edit.dateChanged.connect(lambda _: _on_date_changed())

        def _go_prev():
            d = self._date_edit.date().addDays(-1)
            if d <= DateType.today():
                self._date_edit.setDate(d)

        def _go_next():
            d = self._date_edit.date().addDays(1)
            if d <= DateType.today():
                self._date_edit.setDate(d)

        def _go_today():
            self._date_edit.setDate(DateType.today())

        prev_btn.clicked.connect(_go_prev)
        next_btn.clicked.connect(_go_next)
        today_btn.clicked.connect(_go_today)
