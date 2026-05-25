"""逐步诊断桌面端启动崩溃 — 请用 run-diagnose.bat 运行"""
from __future__ import annotations

import sys
import traceback


def step(msg: str) -> None:
    print(f"[diag] {msg}", flush=True)


def main() -> int:
    step(f"Python {sys.version}")
    step("importing PySide6...")
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

    step("creating QApplication...")
    app = QApplication(sys.argv)
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseOpenGLES, True)
        step("AA_UseOpenGLES set")
    except Exception:
        pass

    # Test 1: bare window
    step("Test 1: bare QLabel window...")
    try:
        w = QLabel("Hello — if you see this, PySide6 works")
        w.setWindowTitle("Diagnostic 1")
        w.resize(400, 200)
        w.show()
        step("  -> OK")
    except Exception:
        traceback.print_exc()
        return 1

    # Test 2: import graph widget
    step("Test 2: importing graphical_trading...")
    try:
        from graphical_trading import GraphicalTradingWidget

        g = GraphicalTradingWidget()
        step("  -> OK")
    except Exception:
        traceback.print_exc()
        return 1

    # Test 3: import sector widget
    step("Test 3: importing sector_trading...")
    try:
        from sector_trading import SectorTradingWidget

        s = SectorTradingWidget()
        step("  -> OK")
    except Exception:
        traceback.print_exc()
        return 1

    # Test 4: import news widget
    step("Test 4: importing news...")
    try:
        from news import NewsWidget

        n = NewsWidget()
        step("  -> OK")
    except Exception:
        traceback.print_exc()
        return 1

    # Test 5: all three in tabs (the real MainWindow)
    step("Test 5: all widgets in QTabWidget...")
    try:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(GraphicalTradingWidget(), "图形交易")
        tabs.addTab(SectorTradingWidget(), "板块交易")
        tabs.addTab(NewsWidget(), "资讯")
        step("  -> OK")
    except Exception:
        traceback.print_exc()
        return 1

    # Test 6: show and run event loop briefly
    step("Test 6: showing window + event loop (3s)...")
    try:
        win = QMainWindow()
        win.setWindowTitle("Diagnostic — Full App")
        win.resize(1280, 800)
        win.setCentralWidget(tabs)
        win.show()
        step("  window shown, starting event loop...")
        QTimer.singleShot(3000, app.quit)
        app.exec()
        step("  event loop exited cleanly")
    except Exception:
        traceback.print_exc()
        return 1

    step("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
