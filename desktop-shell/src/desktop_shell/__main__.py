import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_shell.main_window import MainWindow


def main() -> int:
    print("[boot] starting QApplication...")
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DisableShaderDiskCache, True)
    # 强制使用软件渲染 / OpenGL ES，避免某些显卡驱动导致 STATUS_STACK_BUFFER_OVERRUN
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseOpenGLES, True)
        print("[boot] AA_UseOpenGLES set")
    except Exception:
        pass

    print("[boot] building MainWindow...")
    try:
        window = MainWindow()
    except Exception:
        traceback.print_exc()
        return 1

    print("[boot] showing window...")
    window.show()
    print("[boot] entering event loop...")
    rc = app.exec()
    print("[boot] event loop exited, rc =", rc)
    return rc


if __name__ == "__main__":
    print("[boot] Python version:", sys.version)
    sys.exit(main())
