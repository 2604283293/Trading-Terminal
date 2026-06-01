"""统一主题模块 — qt-material 集成 + A 股配色常量。"""
from __future__ import annotations

# ── A 股交易终端配色 ──────────────────────────────────────────
# Qt-Material 自动处理大部分控件，这里只定义业务语义色

# 涨 / 买 / 多方
UP = "#d83a3a"
UP_BG = "#3d2020"

# 跌 / 卖 / 空方
DOWN = "#2e9f3e"
DOWN_BG = "#1a3020"

# 功能色
WARN = "#e8870a"
INFO = "#2e7fd8"
MUTED = "#888888"
DIM = "#666666"

# 暗色主题下的卡片/面板色
CARD_BG = "#2b2b2b"
CARD_BORDER = "#3a3a3a"
SURFACE_BG = "#252525"
LOG_BG = "#1a1a1a"
LOG_FG = "#c0c0c0"


def apply_theme(app, theme: str = "dark_teal.xml") -> None:
    """应用 qt-material 主题（必须在 QApplication 创建之后调用）。"""
    from qt_material import apply_stylesheet as _apply

    extra = {
        "density_scale": "-1",  # 紧凑模式
        "font_size": "12px",
    }
    _apply(app, theme=theme, extra=extra)


def pct_color(value: float) -> str:
    """根据涨跌返回颜色。正值=红(涨), 负值=绿(跌)。"""
    if value > 0:
        return UP
    elif value < 0:
        return DOWN
    return MUTED
