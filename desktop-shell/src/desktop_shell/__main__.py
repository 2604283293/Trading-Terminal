import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from desktop_shell.config import ensure_data_dirs
from desktop_shell.main_window import MainWindow
from desktop_shell.theme import apply_theme


def main() -> int:
    # 确保数据子目录存在（打包环境下首次启动）
    ensure_data_dirs()

    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DisableShaderDiskCache, True)

    # 字体回落：Win10/Win11 默认字体
    font = QFont("Microsoft YaHei", 9)
    if not font.exactMatch():
        font = QFont("SimHei", 9)
    app.setFont(font)

    # 应用深色专业主题 (qt-material)
    apply_theme(app, theme="dark_teal.xml")

    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseOpenGLES, True)
    except Exception:
        pass

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
