from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class NewsWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(
            "资讯模块\n\n（待开发：新闻聚合、公告检索、关键词订阅）\n\n"
            "数据源：AkShare + RSS"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 15px; color: #666;")
        layout.addWidget(label)
