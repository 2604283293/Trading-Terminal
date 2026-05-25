import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_shell.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DisableShaderDiskCache, True)
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseOpenGLES, True)
    except Exception:
        pass

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
