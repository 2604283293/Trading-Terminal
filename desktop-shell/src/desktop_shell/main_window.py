from PySide6.QtWidgets import QMainWindow, QTabWidget

from graphical_trading import GraphicalTradingWidget
from news import NewsWidget
from sector_trading import SectorTradingWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Terminal")
        self.resize(1280, 800)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        print("[mainwin] creating GraphicalTradingWidget...")
        tabs.addTab(GraphicalTradingWidget(), "图形交易")
        print("[mainwin] creating SectorTradingWidget...")
        tabs.addTab(SectorTradingWidget(), "板块交易")
        print("[mainwin] creating NewsWidget...")
        tabs.addTab(NewsWidget(), "资讯")
        print("[mainwin] all tabs created")
        self.setCentralWidget(tabs)

        self.statusBar().showMessage("就绪 — 数据服务尚未启动（图表使用模拟数据）")
