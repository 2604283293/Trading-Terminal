"""K 线图表 Widget — pyqtgraph 蜡烛图 + TDX 真实数据"""
from __future__ import annotations

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPicture
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from shared.data_sources.tdx_reader import list_codes, read_kline

UP_COLOR = "#d83a3a"
DOWN_COLOR = "#2e9f3e"

PERIOD_LABELS = {"daily": "日线", "1min": "1 分钟"}
PERIOD_KEYS = ["daily", "1min"]

# 预加载股票代码列表（延迟到首次使用）
_code_list: list[str] | None = None


def _get_code_list() -> list[str]:
    global _code_list
    if _code_list is None:
        _code_list = list_codes()
    return _code_list


class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self.data = list(data)
        self.picture = QPicture()
        self._generate_picture()

    def _generate_picture(self):
        painter = QPainter(self.picture)
        body_half_width = 0.3

        for x, o, c, low, high in self.data:
            color = UP_COLOR if c >= o else DOWN_COLOR
            pen = pg.mkPen(color)
            brush = pg.mkBrush(color)
            painter.setPen(pen)
            painter.setBrush(brush)

            painter.drawLine(QPointF(x, low), QPointF(x, high))

            body_top = max(o, c)
            body_bottom = min(o, c)
            body_height = body_top - body_bottom
            if body_height < 1e-9:
                painter.drawLine(
                    QPointF(x - body_half_width, o),
                    QPointF(x + body_half_width, o),
                )
            else:
                painter.drawRect(
                    QRectF(x - body_half_width, body_bottom, body_half_width * 2, body_height)
                )
        painter.end()

    def paint(self, painter, option, widget=None):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


class DateAxis(pg.AxisItem):
    def __init__(self, dates: pd.Series, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dates = dates

    def tickStrings(self, values, scale, spacing):
        labels = []
        n = len(self.dates)
        for v in values:
            idx = int(round(v))
            if 0 <= idx < n:
                labels.append(self.dates.iloc[idx].strftime("%m-%d"))
            else:
                labels.append("")
        return labels


class GraphicalTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        print("[graph] GraphicalTradingWidget.__init__")
        self._current_df: pd.DataFrame | None = None
        self._build_ui()
        # 延迟加载代码列表（不阻塞 UI 启动）
        QTimer.singleShot(50, self._init_code_list)
        print("[graph] _build_ui done")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("股票代码:"))

        self.code_combo = QComboBox()
        self.code_combo.setEditable(True)
        self.code_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.code_combo.setMinimumWidth(160)
        self.code_combo.setPlaceholderText("输入代码如 sh600519")
        self.code_combo.addItems(["sh600519", "sz000001", "sh601318"])
        self.code_combo.setCurrentIndex(-1)
        self.code_combo.currentTextChanged.connect(self._on_code_changed)
        toolbar.addWidget(self.code_combo)

        toolbar.addSpacing(16)
        toolbar.addWidget(QLabel("周期:"))
        self.period_combo = QComboBox()
        self.period_combo.addItems([PERIOD_LABELS[k] for k in PERIOD_KEYS])
        self.period_combo.currentIndexChanged.connect(self._redraw)
        toolbar.addWidget(self.period_combo)

        toolbar.addStretch()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 12px;")
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#fafafa")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("left", "价格")
        layout.addWidget(self.plot_widget, stretch=1)

    def _init_code_list(self):
        """后台加载股票代码列表并设置自动补全。"""
        try:
            codes = _get_code_list()
            completer = QCompleter(codes, self.code_combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.code_combo.setCompleter(completer)
            # 设置默认代码
            if self.code_combo.currentIndex() == -1:
                self.code_combo.setCurrentText("sh600519")
        except Exception:
            pass

    def _on_code_changed(self, text: str):
        code = text.strip()
        if len(code) >= 8:
            self._draw_chart()

    def _period_key(self) -> str:
        idx = self.period_combo.currentIndex()
        return PERIOD_KEYS[idx] if 0 <= idx < len(PERIOD_KEYS) else "daily"

    def _redraw(self):
        self._draw_chart()

    def _draw_chart(self):
        self.plot_widget.clear()
        code = self.code_combo.currentText().strip()
        if not code:
            return

        period = self._period_key()
        try:
            df = read_kline(code, period)
        except FileNotFoundError:
            self.status_label.setText(f"找不到数据: {code} ({PERIOD_LABELS[period]})")
            return
        except Exception as e:
            self.status_label.setText(f"读取失败: {e}")
            return

        if df.empty:
            self.status_label.setText(f"{code} 无 {PERIOD_LABELS[period]} 数据")
            return

        self._current_df = df
        n = len(df)

        if period == "daily":
            candle_data = [
                (i, row.open, row.close, row.low, row.high)
                for i, row in enumerate(df.itertuples())
            ]
            x_label = "日期"
            date_series = df["date"]
        else:
            candle_data = [
                (i, row.open, row.close, row.low, row.high)
                for i, row in enumerate(df.itertuples())
            ]
            x_label = "时间"
            # 分钟线用 date+time 作为标签
            date_series = pd.Series(
                [f"{d} {t}" if t else str(d) for d, t in zip(df["date"], df["time"])]
            )

        self.plot_widget.addItem(CandlestickItem(candle_data))

        date_axis = DateAxis(date_series, orientation="bottom")
        self.plot_widget.setAxisItems({"bottom": date_axis})
        self.plot_widget.setLabel("bottom", x_label)

        # 默认显示最近 80 根 K 线
        self.plot_widget.setXRange(max(0, n - 80), n - 1, padding=0.02)

        first_date = df["date"].iloc[0]
        last_date = df["date"].iloc[-1]
        last_close = df["close"].iloc[-1]
        self.status_label.setText(
            f"{code} · {PERIOD_LABELS[period]} · {n} 根K线 "
            f"({first_date} ~ {last_date}) · 最新价 {last_close:.2f}"
        )
