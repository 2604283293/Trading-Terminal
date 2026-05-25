"""选股筛选器 — 自定义条件扫描全部 A 股日线数据。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shared.screener import CONDITION_TYPES, run_screen, _VIPDOC

# ── 预设策略 ──────────────────────────────────────────────────

PRESETS = {
    "均线金叉": [
        {"type": "ma_cross", "params": {"short": 5, "long": 20, "direction": "up"}},
        {"type": "volume_ratio", "params": {"days": 5, "min_ratio": 1.5}},
        {"type": "price_range", "params": {"min_price": 5.0, "max_price": 200.0}},
    ],
    "放量上涨": [
        {"type": "daily_change", "params": {"min_pct": 3.0, "max_pct": 10.0}},
        {"type": "volume_ratio", "params": {"days": 5, "min_ratio": 2.0}},
        {"type": "price_range", "params": {"min_price": 10.0, "max_price": 100.0}},
    ],
    "强势突破": [
        {"type": "n_day_high", "params": {"days": 20}},
        {"type": "daily_change", "params": {"min_pct": 2.0, "max_pct": 10.0}},
        {"type": "avg_volume", "params": {"days": 5, "min_amount": 1e8}},
    ],
    "连续阳线": [
        {"type": "consecutive_days", "params": {"min_days": 3, "direction": "阳线"}},
        {"type": "price_range", "params": {"min_price": 5.0, "max_price": 200.0}},
    ],
    "20日新高": [
        {"type": "n_day_high", "params": {"days": 20}},
        {"type": "daily_change", "params": {"min_pct": 0.0, "max_pct": 10.0}},
    ],
    "看涨反包": [
        {"type": "engulfing", "params": {"direction": "bullish"}},
        {"type": "price_range", "params": {"min_price": 5.0, "max_price": 200.0}},
        {"type": "avg_volume", "params": {"days": 5, "min_amount": 5e7}},
    ],
}

# ── helpers ────────────────────────────────────────────────────

def _fmt_num(v: float, decimals: int = 2) -> str:
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.{decimals}f}"


class _NumericItem(QTableWidgetItem):
    """表格项 — 显示格式化文本，但按原始数值排序。"""
    def __init__(self, text: str, sort_value: float = 0.0):
        super().__init__(text)
        self._sort_val = sort_value

    def __lt__(self, other: QTableWidgetItem):
        if isinstance(other, _NumericItem):
            return self._sort_val < other._sort_val
        return super().__lt__(other)


class _ScanThread(QThread):
    progress = Signal(int, int, str)
    finished = Signal(list)
    error = Signal(str)
    log_msg = Signal(str)

    def __init__(self, conditions: list[dict]):
        super().__init__()
        self._conditions = conditions

    def run(self) -> None:
        try:
            from shared.screener import _VIPDOC
            total_files = sum(
                sum(1 for f in d.iterdir() if f.suffix == ".day") for mkt in ("sh", "sz", "bj")
                if (d := _VIPDOC / mkt / "lday").exists()
            )
            self.log_msg.emit(f"数据目录: {_VIPDOC}, 共 {total_files} 个 .day 文件")
            self.log_msg.emit(f"条件: {self._conditions}")
            last_pct = -1
            def on_progress(cur: int, total: int, code: str):
                nonlocal last_pct
                pct = cur * 100 // total
                if pct != last_pct:
                    last_pct = pct
                    self.log_msg.emit(f"进度: {cur}/{total} ({pct}%)")
                    self.progress.emit(cur, total, code)

            results = run_screen(self._conditions, on_progress=on_progress)
            self.log_msg.emit(f"扫描完毕，匹配 {len(results)} 只")
            self.finished.emit(results)
        except Exception as exc:
            import traceback
            self.log_msg.emit(f"异常: {traceback.format_exc()}")
            self.error.emit(str(exc))


class GraphicalTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scan_thread: QThread | None = None
        self._condition_widgets: list[dict] = []
        self._results: list = []
        self._build_ui()

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.appendPlainText(f"[{ts}] {msg}")

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(4)

        # ── 第 1 栏：筛选条件区 ────────────────────────────────
        cond_area = QWidget()
        cond_layout = QVBoxLayout(cond_area)
        cond_layout.setContentsMargins(8, 8, 8, 4)
        cond_layout.setSpacing(6)

        # 预设快捷按钮
        preset_bar = QHBoxLayout()
        preset_bar.addWidget(QLabel("快捷预设:"))
        for name in PRESETS:
            btn = QPushButton(name)
            btn.setStyleSheet(
                "QPushButton { padding: 4px 12px; border: 1px solid #ccc; "
                "border-radius: 3px; background: #f8f8f8; }"
                "QPushButton:hover { background: #ffe0e0; border-color: #d83a3a; }"
            )
            btn.clicked.connect(lambda checked, n=name: self._load_preset(n))
            preset_bar.addWidget(btn)

        clear_btn = QPushButton("清空条件")
        clear_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; border: 1px solid #ddd; "
            "border-radius: 3px; color: #999; background: transparent; }"
            "QPushButton:hover { color: #d83a3a; border-color: #d83a3a; }"
        )
        clear_btn.clicked.connect(self._clear_all_conditions)
        preset_bar.addWidget(clear_btn)
        preset_bar.addStretch()
        cond_layout.addLayout(preset_bar)

        # 自定义添加
        custom_bar = QHBoxLayout()
        self.add_combo = QComboBox()
        for ctype, info in CONDITION_TYPES.items():
            self.add_combo.addItem(info["label"], ctype)
        custom_bar.addWidget(QLabel("自定义添加:"))
        custom_bar.addWidget(self.add_combo)

        add_btn = QPushButton("+ 添加")
        add_btn.clicked.connect(lambda: self._add_condition(self.add_combo.currentData()))
        custom_bar.addWidget(add_btn)
        custom_bar.addStretch()

        hint = QLabel("提示：先点上方预设按钮快速填充，再调参数后点筛选")
        hint.setStyleSheet("color: #aaa; font-size: 11px;")
        custom_bar.addWidget(hint)
        cond_layout.addLayout(custom_bar)

        # 条件卡片（可滚动，高度自适应）
        cond_scroll = QScrollArea()
        cond_scroll.setWidgetResizable(True)
        cond_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cond_container = QWidget()
        self._cond_layout = QVBoxLayout(self._cond_container)
        self._cond_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cond_layout.setSpacing(4)
        self._cond_layout.setContentsMargins(4, 4, 4, 4)
        cond_scroll.setWidget(self._cond_container)
        cond_layout.addWidget(cond_scroll)

        # 筛选按钮 + 进度
        action_bar = QHBoxLayout()
        self.scan_btn = QPushButton("开始筛选")
        self.scan_btn.setStyleSheet(
            "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
            "padding: 6px 24px; border-radius: 4px; font-size: 14px; }"
            "QPushButton:hover { background: #c13030; }"
            "QPushButton:disabled { background: #ccc; }"
        )
        self.scan_btn.clicked.connect(self._start_scan)
        action_bar.addWidget(self.scan_btn)
        action_bar.addSpacing(12)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #888; font-size: 12px;")
        action_bar.addWidget(self.progress_label)
        action_bar.addStretch()
        cond_layout.addLayout(action_bar)

        splitter.addWidget(cond_area)

        # ── 第 2 栏：结果表格 ──────────────────────────────────
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
        splitter.addWidget(self._table)

        # ── 第 3 栏：日志输出 ──────────────────────────────────
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(8, 0, 8, 8)
        log_layout.setSpacing(4)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("运行日志:"))
        clear_log_btn = QPushButton("清空")
        clear_log_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; border: 1px solid #ddd; border-radius: 2px; color: #888; }"
            "QPushButton:hover { color: #333; border-color: #999; }"
        )
        log_header.addWidget(clear_log_btn)
        log_header.addStretch()
        log_layout.addLayout(log_header)
        self._log_widget = QPlainTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumBlockCount(2000)
        self._log_widget.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #ccc; font-family: Consolas, monospace; font-size: 11px; }"
        )
        clear_log_btn.clicked.connect(self._log_widget.clear)
        log_layout.addWidget(self._log_widget)
        splitter.addWidget(log_widget)

        # 比例：条件区 2 : 表格 5 : 日志 2
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._log(f"程序启动，数据目录: {_VIPDOC}")

        # 默认加载「均线金叉」预设（必须在 log_widget 创建之后）
        self._load_preset("均线金叉")

    # ── preset ─────────────────────────────────────────────────

    def _load_preset(self, name: str):
        self._clear_all_conditions()
        self._log(f"加载预设: {name}")
        for cond in PRESETS[name]:
            self._add_condition(cond["type"], cond.get("params", {}))

    def _clear_all_conditions(self):
        while self._condition_widgets:
            w = self._condition_widgets.pop()
            self._cond_layout.removeWidget(w["row"])
            w["row"].deleteLater()

    # ── condition builders ─────────────────────────────────────

    def _add_condition(self, ctype: str, override_params: dict | None = None):
        info = CONDITION_TYPES[ctype]
        row_w = QWidget()
        row = QHBoxLayout(row_w)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(8)

        label = QLabel(info["label"])
        label.setStyleSheet("font-weight: bold; color: #d83a3a;")
        label.setFixedWidth(80)
        row.addWidget(label)

        widgets = {"type": ctype, "row": row_w}
        params = {**info["params"], **(override_params or {})}

        if ctype == "daily_change":
            w1 = QDoubleSpinBox(); w1.setRange(-10, 10); w1.setValue(params["min_pct"])
            w1.setSuffix("%"); w1.setDecimals(1)
            w2 = QDoubleSpinBox(); w2.setRange(-10, 10); w2.setValue(params["max_pct"])
            w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(QLabel("涨幅")); row.addWidget(w1)
            row.addWidget(QLabel("~")); row.addWidget(w2)
            widgets["min_pct"] = w1; widgets["max_pct"] = w2

        elif ctype == "n_day_change":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日")
            w2 = QDoubleSpinBox(); w2.setRange(-50, 500); w2.setValue(params["min_pct"])
            w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(QLabel("最近")); row.addWidget(w1)
            row.addWidget(QLabel("累计涨 ≥")); row.addWidget(w2)
            widgets["days"] = w1; widgets["min_pct"] = w2

        elif ctype == "volume_ratio":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日")
            w2 = QDoubleSpinBox(); w2.setRange(0.1, 50); w2.setValue(params["min_ratio"])
            w2.setDecimals(1); w2.setSingleStep(0.5)
            row.addWidget(QLabel("基于")); row.addWidget(w1)
            row.addWidget(QLabel("均量, 今日 ≥")); row.addWidget(w2); row.addWidget(QLabel("倍"))
            widgets["days"] = w1; widgets["min_ratio"] = w2

        elif ctype == "consecutive_days":
            w1 = QSpinBox(); w1.setRange(2, 20); w1.setValue(params["min_days"]); w1.setSuffix("根")
            w2 = QComboBox(); w2.addItems(["阳线", "阴线"]); w2.setCurrentText(params["direction"])
            row.addWidget(QLabel("连续 ≥")); row.addWidget(w1)
            row.addWidget(w2)
            widgets["min_days"] = w1; widgets["direction"] = w2

        elif ctype == "price_range":
            w1 = QDoubleSpinBox(); w1.setRange(0, 10000); w1.setValue(params["min_price"])
            w1.setDecimals(2); w1.setPrefix("¥")
            w2 = QDoubleSpinBox(); w2.setRange(0, 10000); w2.setValue(params["max_price"])
            w2.setDecimals(2); w2.setPrefix("¥")
            row.addWidget(QLabel("价格")); row.addWidget(w1)
            row.addWidget(QLabel("~")); row.addWidget(w2)
            widgets["min_price"] = w1; widgets["max_price"] = w2

        elif ctype == "n_day_high":
            w1 = QSpinBox(); w1.setRange(5, 250); w1.setValue(params["days"]); w1.setSuffix("日")
            row.addWidget(QLabel("今日收盘 > 最近")); row.addWidget(w1); row.addWidget(QLabel("最高价"))
            widgets["days"] = w1

        elif ctype == "n_day_low":
            w1 = QSpinBox(); w1.setRange(5, 250); w1.setValue(params["days"]); w1.setSuffix("日")
            row.addWidget(QLabel("今日收盘 < 最近")); row.addWidget(w1); row.addWidget(QLabel("最低价"))
            widgets["days"] = w1

        elif ctype == "avg_volume":
            w1 = QSpinBox(); w1.setRange(1, 60); w1.setValue(params["days"]); w1.setSuffix("日")
            w2 = QDoubleSpinBox(); w2.setRange(0, 1e12); w2.setValue(params["min_amount"])
            w2.setDecimals(0); w2.setPrefix("¥"); w2.setSingleStep(1e7)
            row.addWidget(QLabel("最近")); row.addWidget(w1)
            row.addWidget(QLabel("日均成交额 ≥")); row.addWidget(w2)
            widgets["days"] = w1; widgets["min_amount"] = w2

        elif ctype == "ma_cross":
            w1 = QSpinBox(); w1.setRange(2, 120); w1.setValue(params["short"]); w1.setPrefix("MA")
            w2 = QSpinBox(); w2.setRange(3, 250); w2.setValue(params["long"]); w2.setPrefix("MA")
            w3 = QComboBox(); w3.addItems(["金叉 ↑", "死叉 ↓"])
            direction = params.get("direction", "up")
            w3.setCurrentText("金叉 ↑" if direction == "up" else "死叉 ↓")
            row.addWidget(w1); row.addWidget(QLabel("上穿" if direction == "up" else "下穿"))
            row.addWidget(w2)
            widgets["short"] = w1; widgets["long"] = w2; widgets["direction"] = w3

        elif ctype == "gap":
            w1 = QComboBox(); w1.addItems(["向上跳空", "向下跳空"])
            direction = params.get("direction", "up")
            w1.setCurrentText("向上跳空" if direction == "up" else "向下跳空")
            w2 = QDoubleSpinBox(); w2.setRange(0, 20); w2.setValue(params["min_pct"])
            w2.setSuffix("%"); w2.setDecimals(1)
            row.addWidget(w1); row.addWidget(QLabel("幅度 ≥")); row.addWidget(w2)
            widgets["direction"] = w1; widgets["min_pct"] = w2

        elif ctype == "engulfing":
            w1 = QComboBox(); w1.addItems(["看涨反包", "看跌反包"])
            direction = params.get("direction", "bullish")
            w1.setCurrentText("看涨反包" if direction == "bullish" else "看跌反包")
            row.addWidget(QLabel("形态:")); row.addWidget(w1)
            widgets["direction"] = w1

        del_btn = QPushButton("×")
        del_btn.setFixedWidth(24)
        del_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 16px; }"
            "QPushButton:hover { color: #d83a3a; }"
        )
        del_btn.clicked.connect(lambda: self._remove_condition(row_w))
        row.addWidget(del_btn)
        row.addStretch()

        self._cond_layout.addWidget(row_w)
        self._condition_widgets.append(widgets)

    def _remove_condition(self, row_w: QWidget):
        self._cond_layout.removeWidget(row_w)
        row_w.deleteLater()
        self._condition_widgets = [c for c in self._condition_widgets if c["row"] is not row_w]

    # ── collect params ─────────────────────────────────────────

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
                    # normalize direction values
                    if val in ("阳线", "阴线"):
                        params[key] = val
                    elif "金叉" in val:
                        params[key] = "up"
                    elif "死叉" in val:
                        params[key] = "down"
                    elif "向上" in val:
                        params[key] = "up"
                    elif "向下" in val:
                        params[key] = "down"
                    elif "看涨" in val:
                        params[key] = "bullish"
                    elif "看跌" in val:
                        params[key] = "bearish"
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
            self._log("已有扫描任务运行中，忽略")
            return

        conditions = self._collect_conditions()
        if not conditions:
            self.progress_label.setText("请先添加至少一个条件")
            self._log("错误: 没有添加任何筛选条件")
            return

        self._log(f"开始扫描，条件数: {len(conditions)}")
        for c in conditions:
            self._log(f"  - {CONDITION_TYPES[c['type']]['label']}: {c['params']}")

        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("筛选中…")
        self._table.setRowCount(0)
        self._results = []

        self._scan_thread = _ScanThread(conditions)
        self._scan_thread.log_msg.connect(self._log)
        self._scan_thread.progress.connect(self._on_progress)
        self._scan_thread.finished.connect(self._on_scan_done)
        self._scan_thread.error.connect(self._on_scan_error)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()
        self._log("工作线程已启动")

    def _on_progress(self, cur: int, total: int, code: str):
        self.progress_label.setText(f"扫描中… {cur}/{total}  ({code})")

    def _on_scan_error(self, msg: str):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("开始筛选")
        self._scan_thread = None
        self._log(f"扫描错误: {msg}")
        self.progress_label.setText(f"扫描出错: {msg}")

    def _on_scan_done(self, results: list):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("开始筛选")
        self._results = results
        self._log(f"扫描完成 — 共 {len(results)} 只标的符合条件")
        self.progress_label.setText(f"扫描完成 — 共 {len(results)} 只标的符合条件")
        self._scan_thread = None

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(results))
        for i, r in enumerate(results):
            m = r.metrics
            # (display_text, sort_value) — sort_value 用于数值排序
            cols = [
                (r.code, 0.0),                              # 0: 代码 (文本排序)
                (m["date"], 0.0),                            # 1: 日期 (文本排序)
                (f"{m['close']:.2f}", m["close"]),           # 2: 收盘价
                (f"{m['change_pct']:+.2f}", m["change_pct"]),# 3: 涨跌幅%
                (f"{m['volume_ratio']:.2f}", m["volume_ratio"]), # 4: 量比
                (_fmt_num(m["amount"]), m["amount"]),        # 5: 成交额
                (f"{m['ma5']:.2f}", m["ma5"]),               # 6: MA5
                (f"{m['ma20']:.2f}", m["ma20"]),             # 7: MA20
                (f"{m['high_20']:.2f}", m["high_20"]),       # 8: 20日高
            ]
            for j, (text, sort_val) in enumerate(cols):
                item = _NumericItem(text, sort_val) if j >= 2 else QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    v = m["change_pct"]
                    if v > 0:
                        item.setForeground(Qt.GlobalColor.red)
                    elif v < 0:
                        item.setForeground(Qt.GlobalColor.darkGreen)
                self._table.setItem(i, j, item)
        self._table.setSortingEnabled(True)
