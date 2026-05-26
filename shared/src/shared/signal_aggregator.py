"""信号聚合引擎 — 多源共振评分。

评分维度:
  - 多源确认 (sources ≥ 2): 30 分
  - 主题质量 (关联主线/热点主题): 25 分
  - 主力资金 (龙虎榜净买入方向): 20 分
  - 涨幅强度: 15 分
  - 主题关联数: 10 分
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.noise_filter import CleanStock, CleanTheme


def score_stocks(
    stocks: list["CleanStock"],
    themes: list["CleanTheme"],
) -> list["CleanStock"]:
    """计算个股共振评分，返回带 signal_score 的个股列表。"""
    if not stocks:
        return stocks

    theme_quality: dict[str, str] = {}
    for t in themes:
        theme_quality[t.name] = t.quality

    quality_weight = {"main_line": 1.0, "hot": 0.85, "new": 0.7, "normal": 0.5}

    for s in stocks:
        score = 0.0

        # ── 多源确认 (0-30) ──
        n_sources = len(set(s.sources))
        if n_sources >= 3:
            score += 30
        elif n_sources == 2:
            score += 20
        elif n_sources == 1:
            score += 10

        # ── 主题质量 (0-25) ──
        best_quality = 0.0
        for theme_name in s.themes:
            q = theme_quality.get(theme_name, "normal")
            w = quality_weight.get(q, 0.5)
            if w > best_quality:
                best_quality = w
        score += best_quality * 25

        # ── 主力资金 (0-20) ──
        if s.net_buy > 1e8:       # > 1亿
            score += 20
        elif s.net_buy > 5e7:     # > 5000万
            score += 15
        elif s.net_buy > 1e7:     # > 1000万
            score += 10
        elif s.net_buy > 0:
            score += 5
        elif s.net_buy < -5e7:    # 净卖出 > 5000万
            score -= 5

        # ── 涨幅强度 (0-15) ──
        chg = abs(s.change_pct)
        if chg >= 9.9:
            score += 15
        elif chg >= 7:
            score += 12
        elif chg >= 5:
            score += 8
        elif chg >= 3:
            score += 4

        # ── 主题关联数 (0-10) ──
        n_themes = len(s.themes)
        if n_themes >= 3:
            score += 10
        elif n_themes == 2:
            score += 7
        elif n_themes == 1:
            score += 4

        s.signal_score = max(0, min(100, int(score)))

    stocks.sort(key=lambda x: x.signal_score, reverse=True)
    return stocks
