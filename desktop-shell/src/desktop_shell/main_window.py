"""Trading Terminal 主窗口。"""
from __future__ import annotations

from datetime import date as DateType

from PySide6.QtCore import Qt, QTimer
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

from desktop_shell.feedback_tab import FeedbackWidget
from desktop_shell.config import APP_VERSION
from desktop_shell.theme import UP, SURFACE_BG, CARD_BORDER, MUTED, DIM
from graphical_trading import GraphicalTradingWidget
from news import NewsWidget
from sector_trading import SectorTradingWidget


def _latest_cached_date() -> DateType:
    """返回最新的缓存交易日，无缓存时返回今天。"""
    try:
        from shared.local_store import list_cached_dates
        dates = list_cached_dates()
        return dates[-1] if dates else DateType.today()
    except Exception:
        return DateType.today()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Terminal")
        self.resize(1280, 800)

        # 启动时定位到最新缓存交易日
        launch_date = _latest_cached_date()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 日期导航条 ──
        nav = QWidget()
        nav.setStyleSheet(f"QWidget {{ background: {SURFACE_BG}; border-bottom: 1px solid {CARD_BORDER}; }}")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 6, 12, 6)
        nav_layout.setSpacing(6)

        prev_btn = QPushButton("<")
        prev_btn.setFixedWidth(28)
        prev_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {CARD_BORDER}; border-radius: 3px; background: #333; "
            f"color: #ccc; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #444; }}"
        )
        nav_layout.addWidget(prev_btn)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setMaximumDate(DateType.today())
        self._date_edit.setDate(launch_date)
        self._date_edit.setStyleSheet(
            f"QDateEdit {{ border: 1px solid {CARD_BORDER}; border-radius: 3px; padding: 3px 6px; "
            f"background: #333; font-size: 13px; color: #ddd; }}"
            f"QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; "
            f"width: 20px; border-left: 1px solid {CARD_BORDER}; }}"
            f"QDateEdit::down-arrow {{ image: none; border-left: 4px solid transparent; "
            f"border-right: 4px solid transparent; border-top: 5px solid #888; "
            f"margin-right: 4px; }}"
        )
        cal = self._date_edit.calendarWidget()
        cal.setStyleSheet(
            f"QCalendarWidget {{ background: #2a2a2a; color: #ddd; }}"
            f"QCalendarWidget QToolButton {{ color: #ddd; background: #333; "
            f"border: 1px solid {CARD_BORDER}; border-radius: 3px; padding: 4px 8px; font-weight: bold; }}"
            f"QCalendarWidget QToolButton:hover {{ background: #444; }}"
            f"QCalendarWidget QSpinBox {{ border: 1px solid {CARD_BORDER}; border-radius: 2px; "
            f"padding: 2px 4px; color: #ddd; background: #333; }}"
            f"QCalendarWidget QTableView {{ color: #ddd; background: #2a2a2a; "
            f"selection-background-color: {UP}; selection-color: white; font-size: 12px; "
            f"outline: none; }}"
        )
        nav_layout.addWidget(self._date_edit)

        next_btn = QPushButton(">")
        next_btn.setFixedWidth(28)
        next_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {CARD_BORDER}; border-radius: 3px; background: #333; "
            f"color: #ccc; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #444; }}"
        )
        nav_layout.addWidget(next_btn)

        today_btn = QPushButton("今天")
        today_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {UP}; border-radius: 3px; color: {UP}; "
            f"background: transparent; padding: 3px 10px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #3d2020; }}"
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
        self._feedback = FeedbackWidget()

        self._tabs.addTab(self._graphical, "图形交易")
        self._tabs.addTab(self._sector, "板块交易")
        self._tabs.addTab(self._news, "资讯")
        self._tabs.addTab(self._feedback, "需求反馈")
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
        _on_date_changed()  # 显式通知所有 tab 当前日期，因为 setDate() 在 tab 创建之前就已触发

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

        # ── 自动更新检查 ──
        from desktop_shell.update_checker import UpdateChecker
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_available)
        QTimer.singleShot(3000, self._update_checker.check)

        self.statusBar().showMessage(
            f"就绪 — v{APP_VERSION} — 数据来源：本地 Parquet 文件"
        )

    def _on_update_available(self, new_version: str, download_url: str):
        """后台静默下载更新，完成后自动退出并安装。"""
        if not download_url:
            return

        self.statusBar().showMessage(f"发现新版本 v{new_version}，正在后台下载…")

        from desktop_shell.update_checker import download_and_install
        from PySide6.QtCore import QThread, Signal

        class _DownloadThread(QThread):
            progress = Signal(int, int)

            def __init__(self, url, ver):
                super().__init__()
                self._url = url
                self._ver = ver

            def run(self):
                download_and_install(
                    self._url, self._ver,
                    on_progress=lambda cur, total: self.progress.emit(cur, total),
                )

        self._dl_thread = _DownloadThread(download_url, new_version)
        self._dl_thread.progress.connect(
            lambda cur, total: self.statusBar().showMessage(
                f"下载更新中… {cur / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB"
            )
        )
        self._dl_thread.finished.connect(self._on_download_done)
        self._dl_thread.start()

    def _on_download_done(self):
        """下载完成，退出应用让批处理执行安装。"""
        self.statusBar().showMessage("更新已就绪，即将自动安装…")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        QTimer.singleShot(1000, QApplication.instance().quit)
