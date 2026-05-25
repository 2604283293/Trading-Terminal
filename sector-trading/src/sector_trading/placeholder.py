from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SectorTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(
            "板块交易模块\n\n（待开发：板块涨跌热力图、概念股清单、资金流监控）\n\n"
            "数据源：Tushare Pro（板块/概念）"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 15px; color: #666;")
        layout.addWidget(label)
