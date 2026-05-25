"""K 线图表 Widget — 使用 pyqtgraph 渲染蜡烛图（A 股惯例：红涨绿跌）"""
from __future__ import annotations

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPicture
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from graphical_trading.mock_data import generate_mock_klines

UP_COLOR = "#d83a3a"
DOWN_COLOR = "#2e9f3e"


class CandlestickItem(pg.GraphicsObject):
    """蜡烛图绘制项。data: iterable of (x, open, close, low, high)。"""

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
    """X 轴用日期显示，底层是整数索引。"""

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
        self._build_ui()
        self._draw_chart()
        print("[graph] _draw_chart done")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("股票代码:"))
        self.code_combo = QComboBox()
        self.code_combo.addItems(
            [
                "sh600519 贵州茅台（模拟）",
                "sz000001 平安银行（模拟）",
                "sh601318 中国平安（模拟）",
            ]
        )
        self.code_combo.currentIndexChanged.connect(self._redraw)
        toolbar.addWidget(self.code_combo)

        toolbar.addSpacing(16)
        toolbar.addWidget(QLabel("周期:"))
        self.period_combo = QComboBox()
        self.period_combo.addItems(["日线", "5 分钟", "1 分钟"])
        self.period_combo.currentIndexChanged.connect(self._redraw)
        toolbar.addWidget(self.period_combo)

        toolbar.addStretch()
        warn = QLabel("⚠ 当前为模拟数据，等通达信下载完毕后切到真实行情")
        warn.setStyleSheet("color: #b67500;")
        toolbar.addWidget(warn)
        layout.addLayout(toolbar)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#fafafa")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("left", "价格")
        layout.addWidget(self.plot_widget, stretch=1)

    def _redraw(self):
        self._draw_chart()

    def _draw_chart(self):
        self.plot_widget.clear()

        seed = self.code_combo.currentIndex() * 7 + self.period_combo.currentIndex() * 13 + 42
        base_price = 50 + self.code_combo.currentIndex() * 30
        n = {"日线": 120, "5 分钟": 240, "1 分钟": 240}[self.period_combo.currentText()]
        df = generate_mock_klines(n=n, start_price=base_price, seed=seed)

        candle_data = [
            (i, row.open, row.close, row.low, row.high) for i, row in enumerate(df.itertuples())
        ]
        self.plot_widget.addItem(CandlestickItem(candle_data))

        date_axis = DateAxis(df["date"], orientation="bottom")
        self.plot_widget.setAxisItems({"bottom": date_axis})
        self.plot_widget.setLabel("bottom", "日期" if self.period_combo.currentIndex() == 0 else "时间")

        self.plot_widget.setXRange(max(0, len(df) - 80), len(df) - 1, padding=0.02)
