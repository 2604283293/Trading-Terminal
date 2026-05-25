"""选股筛选器 — 自定义条件扫描全部 A 股日线数据。"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shared.screener import CONDITION_TYPES, run_screen


def _fmt_num(v: float, decimals: int = 2) -> str:
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.{decimals}f}"


class _ScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(self, conditions: list[dict]):
        super().__init__()
        self._conditions = conditions

    def run(self) -> None:
        results = run_screen(
            self._conditions,
            on_progress=lambda cur, total, code: self.progress.emit(cur, total, code),
        )
        self.finished.emit(results)


class GraphicalTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scan_thread: QThread | None = None
        self._condition_widgets: list[dict] = []
        self._results: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # === 顶部工具栏 ===
        toolbar = QHBoxLayout()

        add_combo = QComboBox()
        for ctype, info in CONDITION_TYPES.items():
            add_combo.addItem(info["label"], ctype)
        toolbar.addWidget(QLabel("添加条件:"))
        toolbar.addWidget(add_combo)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(lambda: self._add_condition(add_combo.currentData()))
        toolbar.addWidget(add_btn)

        toolbar.addSpacing(20)

        self.scan_btn = QPushButton("开始筛选")
        self.scan_btn.setStyleSheet(
            "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
            "padding: 6px 20px; border-radius: 4px; }"
            "QPushButton:hover { background: #c13030; }"
            "QPushButton:disabled { background: #ccc; }"
        )
        self.scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self.scan_btn)

        toolbar.addStretch()
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #888; font-size: 12px;")
        toolbar.addWidget(self.progress_label)

        layout.addLayout(toolbar)

        # === 条件列表（可滚动）===
        cond_scroll = QScrollArea()
        cond_scroll.setMaximumHeight(200)
        cond_scroll.setWidgetResizable(True)
        cond_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cond_container = QWidget()
        self._cond_layout = QVBoxLayout(self._cond_container)
        self._cond_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cond_layout.setSpacing(4)
        self._cond_layout.setContentsMargins(0, 0, 0, 0)
        cond_scroll.setWidget(self._cond_container)
        layout.addWidget(cond_scroll)

        # 默认加一个条件
        self._add_condition("daily_change")

        # === 结果表格 ===
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "代码", "日期", "收盘价", "涨跌幅%", "量比", "成交额", "MA5", "MA20", "20日高"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(9):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, stretch=1)

    # ── condition UI ──────────────────────────────────────────

    def _add_condition(self, ctype: str):
        info = CONDITION_TYPES[ctype]
        row_w = QWidget()
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        # 标签
        label = QLabel(info["label"])
        label.setStyleSheet("font-weight: bold; color: #d83a3a;")
        label.setFixedWidth(80)
        row.addWidget(label)

        widgets = {"type": ctype, "row": row_w}

        params = info["params"]
        if ctype == "daily_change":
            w1 = QDoubleSpinBox()
            w1.setRange(-10, 10); w1.setValue(params["min_pct"]); w1.setSuffix("%"); w1.setDecimals(1)
            w2 = QDoubleSpinBox()
            w2.setRange(-10, 10); w2.setValue(params["max_pct"]); w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(QLabel("从")); row.addWidget(w1)
            row.addWidget(QLabel("到")); row.addWidget(w2)
            widgets["min_pct"] = w1; widgets["max_pct"] = w2

        elif ctype == "n_day_change":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日")
            w2 = QDoubleSpinBox(); w2.setRange(-50, 500); w2.setValue(params["min_pct"]); w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(QLabel("最近")); row.addWidget(w1)
            row.addWidget(QLabel("涨幅≥")); row.addWidget(w2)
            widgets["days"] = w1; widgets["min_pct"] = w2

        elif ctype == "volume_ratio":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日均量")
            w2 = QDoubleSpinBox(); w2.setRange(0.1, 50); w2.setValue(params["min_ratio"]); w2.setDecimals(1); w2.setSingleStep(0.5)
            row.addWidget(QLabel("基于")); row.addWidget(w1)
            row.addWidget(QLabel("倍率≥")); row.addWidget(w2)
            widgets["days"] = w1; widgets["min_ratio"] = w2

        elif ctype == "consecutive_days":
            w1 = QSpinBox(); w1.setRange(2, 20); w1.setValue(params["min_days"]); w1.setSuffix("根")
            w2 = QComboBox(); w2.addItems(["阳线", "阴线"])
            w2.setCurrentText(params["direction"])
            row.addWidget(QLabel("连续")); row.addWidget(w1)
            row.addWidget(w2)
            widgets["min_days"] = w1; widgets["direction"] = w2

        elif ctype == "price_range":
            w1 = QDoubleSpinBox(); w1.setRange(0, 10000); w1.setValue(params["min_price"]); w1.setDecimals(2); w1.setPrefix("¥")
            w2 = QDoubleSpinBox(); w2.setRange(0, 10000); w2.setValue(params["max_price"]); w2.setDecimals(2); w2.setPrefix("¥")
            row.addWidget(QLabel("从")); row.addWidget(w1)
            row.addWidget(QLabel("到")); row.addWidget(w2)
            widgets["min_price"] = w1; widgets["max_price"] = w2

        elif ctype in ("n_day_high", "n_day_low"):
            w1 = QSpinBox(); w1.setRange(5, 250); w1.setValue(params["days"]); w1.setSuffix("日")
            row.addWidget(QLabel("最近")); row.addWidget(w1)
            widgets["days"] = w1

        elif ctype == "avg_volume":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日")
            w2 = QDoubleSpinBox(); w2.setRange(0, 1e12); w2.setValue(params["min_amount"]); w2.setDecimals(0); w2.setPrefix("¥"); w2.setSingleStep(1e7)
            row.addWidget(QLabel("最近")); row.addWidget(w1)
            row.addWidget(QLabel("日均≥")); row.addWidget(w2)
            widgets["days"] = w1; widgets["min_amount"] = w2

        elif ctype == "ma_cross":
            w1 = QSpinBox(); w1.setRange(2, 120); w1.setValue(params["short"])
            w2 = QSpinBox(); w2.setRange(3, 250); w2.setValue(params["long"])
            w3 = QComboBox(); w3.addItems(["up (金叉)", "down (死叉)"])
            w3.setCurrentText(params["direction"] if isinstance(params["direction"], str) else "up")
            row.addWidget(QLabel("MA")); row.addWidget(w1)
            row.addWidget(QLabel("与 MA")); row.addWidget(w2)
            row.addWidget(w3)
            widgets["short"] = w1; widgets["long"] = w2; widgets["direction"] = w3

        elif ctype == "gap":
            w1 = QComboBox(); w1.addItems(["up (向上)", "down (向下)"])
            w1.setCurrentText(params["direction"] if isinstance(params["direction"], str) else "up")
            w2 = QDoubleSpinBox(); w2.setRange(0, 20); w2.setValue(params["min_pct"]); w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(QLabel("方向")); row.addWidget(w1)
            row.addWidget(QLabel("幅度≥")); row.addWidget(w2)
            widgets["direction"] = w1; widgets["min_pct"] = w2

        # 删除按钮
        del_btn = QPushButton("×")
        del_btn.setFixedWidth(24)
        del_btn.setStyleSheet("QPushButton { color: #999; border: none; font-size: 16px; } QPushButton:hover { color: #d83a3a; }")
        del_btn.clicked.connect(lambda: self._remove_condition(row_w))
        row.addWidget(del_btn)
        row.addStretch()

        self._cond_layout.addWidget(row_w)
        self._condition_widgets.append(widgets)

    def _remove_condition(self, row_w: QWidget):
        self._cond_layout.removeWidget(row_w)
        row_w.deleteLater()
        self._condition_widgets = [
            c for c in self._condition_widgets if c["row"] is not row_w
        ]

    def _collect_conditions(self) -> list[dict]:
        conditions = []
        for w in self._condition_widgets:
            params = {}
            ctype = w["type"]
            for key, widget in w.items():
                if key in ("type", "row"):
                    continue
                if isinstance(widget, QComboBox):
                    val = widget.currentText()
                    # Strip hints like "up (金叉)"
                    if " " in val:
                        val = val.split(" ")[0]
                    if val in ("阳线", "阴线"):
                        params[key] = val
                    elif val in ("up", "down"):
                        params[key] = val
                    else:
                        try:
                            params[key] = float(val)
                        except ValueError:
                            params[key] = val
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    params[key] = widget.value()
            conditions.append({"type": ctype, "params": params})
        return conditions

    # ── scan ──────────────────────────────────────────────────

    def _start_scan(self):
        if self._scan_thread is not None:
            return

        conditions = self._collect_conditions()
        if not conditions:
            return

        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("筛选中…")
        self._table.setRowCount(0)
        self._results = []

        self._scan_thread = QThread()
        worker = _ScanWorker(conditions)
        worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_scan_done)
        worker.finished.connect(self._scan_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _on_progress(self, cur: int, total: int, code: str):
        self.progress_label.setText(f"扫描中… {cur}/{total}  ({code})")

    def _on_scan_done(self, results: list):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("开始筛选")
        self._scan_thread = None
        self._results = results

        self.progress_label.setText(f"完成 — 共 {len(results)} 只标的条件")

        self._table.setRowCount(len(results))
        for i, r in enumerate(results):
            m = r.metrics
            items = [
                r.code,
                m["date"],
                f"{m['close']:.2f}",
                f"{m['change_pct']:+.2f}",
                f"{m['volume_ratio']:.2f}",
                _fmt_num(m["amount"]),
                f"{m['ma5']:.2f}",
                f"{m['ma20']:.2f}",
                f"{m['high_20']:.2f}",
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 涨跌着色
                if j == 3:
                    try:
                        v = float(text)
                        if v > 0:
                            item.setForeground(Qt.GlobalColor.red)
                        elif v < 0:
                            item.setForeground(Qt.GlobalColor.darkGreen)
                    except ValueError:
                        pass
                self._table.setItem(i, j, item)
