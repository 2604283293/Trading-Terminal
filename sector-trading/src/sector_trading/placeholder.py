"""板块交易 — 多源数据聚合：韭菜公社 + 东方财富(龙虎榜/北向/板块资金)。"""
from __future__ import annotations

from datetime import date as DateType, datetime

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shared.local_store import (
    has_today_data,
    load_actions,
    load_billboard,
    load_northbound,
    load_sector_flow,
    load_stocks,
    save_actions,
    save_billboard,
    save_northbound,
    save_sector_flow,
    save_stocks,
)
from shared.noise_filter import CleanStock, CleanTheme, clean_today


def _fmt_amt(v: float) -> str:
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.0f}"


def _pct_color(v: float) -> str:
    if v > 0:
        return "#d83a3a"
    elif v < 0:
        return "#2e9f3e"
    return "#888"


# ── worker ──────────────────────────────────────────────────────

class _ScrapeWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)

    def __init__(self, target_date: DateType):
        super().__init__()
        self._target = target_date

    def run(self) -> None:
        result = {"ok": True, "actions": 0, "stocks": 0, "billboard": 0,
                  "northbound": 0, "sector_flow": 0, "errors": []}

        # ── 韭菜公社 (Selenium) ──
        try:
            self.progress.emit("正在抓取韭菜公社…")
            from shared.data_sources.jiuyangongshe_selenium import fetch_all
            data = fetch_all(self._target)
            if data["actions"]:
                save_actions(data["actions"], self._target)
                result["actions"] = len(data["actions"])
            if data["stocks"]:
                save_stocks(data["stocks"], self._target)
                result["stocks"] = len(data["stocks"])
        except Exception as exc:
            result["errors"].append(f"韭菜公社: {exc}")

        # ── 东方财富数据 ──
        try:
            from shared.data_pipeline import fetch_all as fetch_em

            self.progress.emit("正在获取龙虎榜…")
            em = fetch_em(self._target, on_progress=lambda msg: self.progress.emit(msg))
            result["billboard"] = len(em.billboard)
            result["northbound"] = len(em.northbound)
            result["sector_flow"] = len(em.sector_flow)
            result["errors"].extend(em.errors)
        except Exception as exc:
            result["errors"].append(f"东方财富: {exc}")

        if result["errors"]:
            result["ok"] = False
        self.finished.emit(result)


# ── widget ──────────────────────────────────────────────────────

class SectorTradingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scrape_thread: QThread | None = None
        self._stocks_df = None
        self._current_date: DateType = DateType.today()
        self._build_ui()
        self._log("板块交易模块启动")
        self._refresh()

    def set_date(self, date: DateType) -> None:
        """切换查看日期（由主窗口日期选择器调用）。"""
        self._current_date = date
        is_today = (date == DateType.today())
        self.scrape_btn.setEnabled(is_today)
        if not is_today:
            self.scrape_btn.setText("历史模式")
            self.scrape_btn.setStyleSheet(
                "QPushButton { background: #888; color: white; font-weight: bold; "
                "padding: 6px 16px; border-radius: 4px; }"
            )
        else:
            self.scrape_btn.setText("刷新全部数据")
            self.scrape_btn.setStyleSheet(
                "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
                "padding: 6px 16px; border-radius: 4px; }"
                "QPushButton:hover { background: #c13030; }"
                "QPushButton:disabled { background: #ccc; }"
            )
        self._refresh()

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.appendPlainText(f"[{ts}] {msg}")

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(4)

        # ── 上半：主面板 ──
        top = QWidget()
        layout = QVBoxLayout(top)
        layout.setContentsMargins(12, 12, 12, 4)
        layout.setSpacing(8)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        self.title = QLabel("板块交易")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        toolbar.addWidget(self.title)
        toolbar.addStretch()

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888; font-size: 12px;")
        toolbar.addWidget(self.status)

        self.scrape_btn = QPushButton("刷新全部数据")
        self.scrape_btn.setStyleSheet(
            "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background: #c13030; }"
            "QPushButton:disabled { background: #ccc; }"
        )
        self.scrape_btn.clicked.connect(self._scrape)
        toolbar.addWidget(self.scrape_btn)
        layout.addLayout(toolbar)

        # ── 子 tab ──
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._theme_content = self._make_scroll_area()
        self._billboard_content = self._make_scroll_area()
        self._sector_content = self._make_scroll_area()
        self._northbound_content = self._make_scroll_area()
        self._signal_content = self._make_scroll_area()

        self._tabs.addTab(self._theme_content, "异动主题")
        self._tabs.addTab(self._billboard_content, "龙虎榜")
        self._tabs.addTab(self._sector_content, "板块资金")
        self._tabs.addTab(self._northbound_content, "北向资金")
        self._tabs.addTab(self._signal_content, "综合信号")

        layout.addWidget(self._tabs, stretch=1)

        splitter.addWidget(top)

        # ── 下半：日志面板 ──
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(12, 0, 12, 8)
        log_layout.setSpacing(4)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("运行日志:"))
        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; border: 1px solid #ddd; border-radius: 2px; color: #888; }"
            "QPushButton:hover { color: #333; border-color: #999; }"
        )
        log_header.addWidget(clear_btn)
        log_header.addStretch()
        log_layout.addLayout(log_header)
        self._log_widget = QPlainTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumBlockCount(2000)
        self._log_widget.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #ccc; font-family: Consolas, monospace; font-size: 11px; }"
        )
        clear_btn.clicked.connect(self._log_widget.clear)
        log_layout.addWidget(self._log_widget)
        splitter.addWidget(log_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

    def _make_scroll_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_layout.setSpacing(8)
        scroll.setWidget(content)
        scroll.content_layout = content_layout
        return scroll

    def _clear_tab(self, scroll: QScrollArea):
        layout = scroll.content_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    # ── refresh ───────────────────────────────────────────────────

    def _refresh(self):
        today = self._current_date
        self._log(f"刷新全部数据面板, 日期={today.isoformat()}")
        self.title.setText(f"板块交易 · {today.isoformat()}")

        self._refresh_themes(today)
        self._refresh_billboard(today)
        self._refresh_sector_flow(today)
        self._refresh_northbound(today)
        self._refresh_signals(today)

    def _refresh_themes(self, today: DateType):
        self._clear_tab(self._theme_content)
        layout = self._theme_content.content_layout

        if not has_today_data(today):
            self._show_msg(layout, "暂无数据。点击右上角『刷新全部数据』抓取。")
            self._log("异动主题: 无本地数据")
            return

        actions_df = load_actions(today)
        try:
            self._stocks_df = load_stocks(today)
        except Exception:
            self._stocks_df = None

        n = len(actions_df)
        n_s = 0 if self._stocks_df is None else len(self._stocks_df)
        self._log(f"异动主题: {n} 个题材, {n_s} 只个股")
        self._tabs.setTabText(0, f"异动主题 ({n})")

        for _, item in actions_df.iterrows():
            theme_stocks = None
            if self._stocks_df is not None and len(self._stocks_df) > 0:
                mask = self._stocks_df["theme"] == item["theme"]
                theme_stocks = self._stocks_df[mask]
            layout.addWidget(self._make_theme_card(item, theme_stocks))

    def _refresh_billboard(self, today: DateType):
        self._clear_tab(self._billboard_content)
        layout = self._billboard_content.content_layout

        df = load_billboard(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无龙虎榜数据。")
            return

        self._tabs.setTabText(1, f"龙虎榜 ({len(df)})")

        # 按主力净买入排序
        df = df.sort_values("net_buy", ascending=False)

        for _, row in df.iterrows():
            layout.addWidget(self._make_billboard_card(row))

    def _refresh_sector_flow(self, today: DateType):
        self._clear_tab(self._sector_content)
        layout = self._sector_content.content_layout

        df = load_sector_flow(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无板块资金流数据。")
            return

        self._tabs.setTabText(2, f"板块资金 ({len(df)})")

        for _, row in df.iterrows():
            layout.addWidget(self._make_sector_card(row))

    def _refresh_northbound(self, today: DateType):
        self._clear_tab(self._northbound_content)
        layout = self._northbound_content.content_layout

        df = load_northbound(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无北向资金数据。")
            return

        # 汇总当日净买入
        daily_net = df["net_buy"].sum()
        color = "#d83a3a" if daily_net >= 0 else "#2e9f3e"
        sign = "净流入" if daily_net >= 0 else "净流出"

        summary = QLabel(f"今日北向资金 {sign}  {_fmt_amt(abs(daily_net))}")
        summary.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; padding: 8px 0;")
        layout.addWidget(summary)

        self._tabs.setTabText(3, f"北向资金 {sign}")

    def _refresh_signals(self, today: DateType):
        self._clear_tab(self._signal_content)
        layout = self._signal_content.content_layout

        if not has_today_data(today):
            self._show_msg(layout, "暂无数据。点击右上角『刷新全部数据』抓取。")
            self._log("综合信号: 无本地数据")
            return

        try:
            result = clean_today(today)
        except Exception as exc:
            self._log(f"综合信号计算失败: {exc}")
            self._show_msg(layout, f"数据清洗失败: {exc}")
            return

        themes: list[CleanTheme] = result["themes"]
        stocks: list[CleanStock] = result["stocks"]

        self._tabs.setTabText(4, f"综合信号 ({len(stocks)})")
        self._log(f"综合信号: {len(themes)} 个清洗主题, {len(stocks)} 只评分个股")

        # ── 主题摘要 ──
        main_line = [t for t in themes if t.quality == "main_line"]
        hot = [t for t in themes if t.quality == "hot"]
        new = [t for t in themes if t.quality == "new"]

        summary_text = f"主线 {len(main_line)} 个 · 热点 {len(hot)} 个 · 新题材 {len(new)} 个"
        summary = QLabel(summary_text)
        summary.setStyleSheet("font-size: 13px; color: #555; padding: 4px 0 8px 0;")
        layout.addWidget(summary)

        # ── 主题卡片 ──
        for t in themes:
            if t.quality in ("main_line", "hot"):
                layout.addWidget(self._make_signal_theme_card(t))

        # ── 分隔 ──
        sep = QLabel("── 个股共振评分 ──")
        sep.setStyleSheet("font-size: 14px; font-weight: bold; color: #d83a3a; padding: 12px 0 4px 0;")
        layout.addWidget(sep)

        # ── 评分排序个股 ──
        if stocks:
            layout.addLayout(self._make_signal_stock_table(stocks[:30]))
        else:
            self._show_msg(layout, "暂无共振个股信号。")

    # ── signal cards ────────────────────────────────────────────────

    def _make_signal_theme_card(self, t: CleanTheme) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 10px; }"
        )
        layout = QHBoxLayout(card)
        layout.setSpacing(12)

        quality_tag = {
            "main_line": ("主线", "#d83a3a"),
            "hot": ("热点", "#e8870a"),
            "new": ("新题材", "#2e7fd8"),
        }.get(t.quality, ("普通", "#888"))

        tag = QLabel(quality_tag[0])
        tag.setStyleSheet(
            f"font-size: 11px; color: #fff; background: {quality_tag[1]}; "
            "padding: 2px 8px; border-radius: 3px; font-weight: bold;"
        )
        layout.addWidget(tag)

        name = QLabel(t.name)
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #222;")
        name.setFixedWidth(140)
        layout.addWidget(name)

        info = QLabel(f"{t.stock_count} 只个股 · 持续 {t.persistence_days} 天"
                      f"{' · 放量确认' if t.has_volume_confirmed else ''}")
        info.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(info)

        src_tags = " + ".join(t.sources)
        src = QLabel(src_tags)
        src.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(src)

        layout.addStretch()
        return card

    def _make_signal_stock_table(self, stocks: list[CleanStock]):
        box = QVBoxLayout()
        box.setSpacing(3)
        box.setContentsMargins(8, 4, 0, 0)

        # 表头
        hr = QHBoxLayout()
        for col, w in [("评分", 50), ("名称", 100), ("代码", 75), ("涨跌幅", 75), ("量比", 55),
                        ("主力净买", 90), ("来源", 100), ("关联主题", 160)]:
            lbl = QLabel(col)
            lbl.setStyleSheet("color: #999; font-size: 11px;")
            lbl.setFixedWidth(w)
            hr.addWidget(lbl)
        hr.addStretch()
        box.addLayout(hr)

        for s in stocks:
            row = QHBoxLayout()

            # 评分
            score_color = "#d83a3a" if s.signal_score >= 70 else ("#e8870a" if s.signal_score >= 40 else "#888")
            score_lbl = QLabel(str(s.signal_score))
            score_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {score_color};"
            )
            score_lbl.setFixedWidth(50)
            row.addWidget(score_lbl)

            # 名称
            name_lbl = QLabel(s.name)
            name_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
            name_lbl.setFixedWidth(100)
            row.addWidget(name_lbl)

            # 代码
            code_lbl = QLabel(s.code)
            code_lbl.setStyleSheet("font-size: 11px; color: #888;")
            code_lbl.setFixedWidth(75)
            row.addWidget(code_lbl)

            # 涨跌幅
            chg_color = _pct_color(s.change_pct)
            chg_lbl = QLabel(f"{s.change_pct:+.2f}%")
            chg_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {chg_color};")
            chg_lbl.setFixedWidth(75)
            row.addWidget(chg_lbl)

            # 量比
            vol_lbl = QLabel(f"{s.volume_ratio:.1f}")
            vol_lbl.setStyleSheet("font-size: 12px; color: #555;")
            vol_lbl.setFixedWidth(55)
            row.addWidget(vol_lbl)

            # 主力净买
            net_lbl = QLabel(_fmt_amt(s.net_buy))
            net_lbl.setStyleSheet(f"font-size: 12px; color: {_pct_color(s.net_buy)};")
            net_lbl.setFixedWidth(90)
            row.addWidget(net_lbl)

            # 来源
            src_lbl = QLabel("+".join(s.sources))
            src_lbl.setStyleSheet("font-size: 11px; color: #888;")
            src_lbl.setFixedWidth(100)
            row.addWidget(src_lbl)

            # 关联主题
            theme_text = ", ".join(s.themes[:3])
            if len(s.themes) > 3:
                theme_text += f" +{len(s.themes) - 3}"
            theme_lbl = QLabel(theme_text)
            theme_lbl.setStyleSheet("font-size: 11px; color: #2e7fd8;")
            theme_lbl.setFixedWidth(160)
            row.addWidget(theme_lbl)

            row.addStretch()
            box.addLayout(row)

        return box

    # ── cards ──────────────────────────────────────────────────────

    def _make_theme_card(self, item, theme_stocks) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 12px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        header = QHBoxLayout()
        theme = QLabel(item["theme"])
        theme.setStyleSheet("font-size: 16px; font-weight: bold; color: #222;")
        header.addWidget(theme)
        header.addSpacing(12)
        count = QLabel(f"{item['stock_count']} 只异动")
        count.setStyleSheet("color: #d83a3a; font-size: 13px;")
        header.addWidget(count)
        header.addStretch()
        source = QLabel("@jiuyangongshe")
        source.setStyleSheet("color: #aaa; font-size: 11px;")
        header.addWidget(source)
        layout.addLayout(header)

        if item["summary"]:
            summary = QLabel(item["summary"])
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #444; font-size: 13px;")
            layout.addWidget(summary)

        if theme_stocks is not None and len(theme_stocks) > 0:
            layout.addLayout(self._make_stock_table(theme_stocks))

        return card

    def _make_stock_table(self, stocks_df):
        box = QVBoxLayout()
        box.setSpacing(2)
        box.setContentsMargins(8, 4, 0, 0)

        # 表头
        hr = QHBoxLayout()
        for col, w in [("名称", 100), ("代码", 70), ("最新价", 70), ("涨跌幅", 80), ("涨停时间", 70), ("异动", 80)]:
            lbl = QLabel(col)
            lbl.setStyleSheet("color: #999; font-size: 11px;")
            lbl.setFixedWidth(w)
            hr.addWidget(lbl)
        hr.addStretch()
        box.addLayout(hr)

        for _, s in stocks_df.iterrows():
            row = QHBoxLayout()
            for key, w in [("name", 100), ("code", 70), ("last_price", 70), ("change_pct", 80), ("limit_time", 70), ("action_type", 80)]:
                val = str(s[key])
                lbl = QLabel(val)
                style = "font-size: 12px; color: #333;"
                if key == "name":
                    style = "font-size: 12px; font-weight: bold; color: #333;"
                elif key == "code":
                    style = "font-size: 11px; color: #888;"
                elif key == "change_pct":
                    raw = str(s[key]).replace("%", "")
                    try:
                        v = float(raw)
                    except ValueError:
                        v = 0.0
                    color = _pct_color(v)
                    style = f"font-size: 12px; font-weight: bold; color: {color};"
                elif key == "action_type":
                    style = "font-size: 11px; color: #d83a3a;"
                lbl.setStyleSheet(style)
                lbl.setFixedWidth(w)
                row.addWidget(lbl)
            row.addStretch()
            box.addLayout(row)

        return box

    def _make_billboard_card(self, row) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        # 第一行：名称 + 代码 + 涨跌幅
        h1 = QHBoxLayout()
        name = QLabel(f"{row['name']}  {row['code']}")
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #222;")
        h1.addWidget(name)
        h1.addStretch()
        chg = QLabel(f"{row['change_pct']:+.2f}%")
        chg.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {_pct_color(row['change_pct'])};")
        h1.addWidget(chg)
        layout.addLayout(h1)

        # 第二行：主力净买 + 占比
        h2 = QHBoxLayout()
        net = QLabel(f"主力净买: {_fmt_amt(row['net_buy'])}")
        net.setStyleSheet("font-size: 12px; color: #d83a3a;")
        h2.addWidget(net)
        ratio = QLabel(f"买入占比: {row['buy_ratio']:.1f}%")
        ratio.setStyleSheet("font-size: 12px; color: #888;")
        h2.addWidget(ratio)
        h2.addStretch()
        if row["reason"]:
            reason = QLabel(row["reason"])
            reason.setStyleSheet("font-size: 11px; color: #666; background: #f5f5f5; "
                                "padding: 2px 6px; border-radius: 3px;")
            h2.addWidget(reason)
        layout.addLayout(h2)

        # 第三行：分类净买
        h3 = QHBoxLayout()
        for label, val in [("超大单", row["super_large_net"]), ("大单", row["large_net"]),
                           ("中单", row["medium_net"]), ("小单", row["small_net"])]:
            v = float(val) if val else 0
            c = _pct_color(1) if v >= 0 else _pct_color(-1)
            lbl = QLabel(f"{label}: {_fmt_amt(v)}")
            lbl.setStyleSheet(f"font-size: 11px; color: {c};")
            h3.addWidget(lbl)
            h3.addSpacing(12)
        h3.addStretch()
        layout.addLayout(h3)

        return card

    def _make_sector_card(self, row) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e5e5e5; "
            "border-radius: 6px; padding: 8px 12px; }"
        )
        layout = QHBoxLayout(card)
        layout.setSpacing(16)

        mkt_tag = "概念" if row["market"] == "concept" else "行业"
        tag = QLabel(mkt_tag)
        tag.setStyleSheet("font-size: 10px; color: #fff; background: #888; "
                         "padding: 1px 5px; border-radius: 2px;")
        layout.addWidget(tag)

        name = QLabel(f"{row['name']}")
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #222;")
        name.setFixedWidth(120)
        layout.addWidget(name)

        chg = QLabel(f"{row['change_pct']:+.2f}%")
        chg.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_pct_color(row['change_pct'])};")
        chg.setFixedWidth(80)
        layout.addWidget(chg)

        net = QLabel(f"主力: {_fmt_amt(row['main_net'])}")
        net.setStyleSheet(f"font-size: 12px; color: {_pct_color(row['main_net'])};")
        layout.addWidget(net)

        ratio = QLabel(f"占比: {row['main_ratio']:.1f}%")
        ratio.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(ratio)

        layout.addStretch()
        return card

    # ── scrape ────────────────────────────────────────────────────

    def _scrape(self):
        if self._scrape_thread is not None:
            self._log("已有抓取任务运行中，忽略")
            return
        self._log("===== 开始抓取全部数据 =====")
        self.scrape_btn.setEnabled(False)
        self.scrape_btn.setText("抓取中…")
        self.status.setText("正在拉取数据…")

        self._scrape_thread = QThread()
        worker = _ScrapeWorker(self._current_date)
        worker.moveToThread(self._scrape_thread)
        self._scrape_thread.started.connect(worker.run)
        worker.progress.connect(lambda msg: self.status.setText(msg))
        worker.finished.connect(self._on_scrape_done)
        worker.finished.connect(self._scrape_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._scrape_thread.finished.connect(self._scrape_thread.deleteLater)
        self._scrape_thread.start()

    def _on_scrape_done(self, result: dict):
        self.scrape_btn.setEnabled(True)
        self.scrape_btn.setText("刷新全部数据")
        self._scrape_thread = None

        msgs = []
        if result["actions"]:
            msgs.append(f"异动主题: {result['actions']}")
        if result["billboard"]:
            msgs.append(f"龙虎榜: {result['billboard']}")
        if result["sector_flow"]:
            msgs.append(f"板块资金: {result['sector_flow']}")
        if result["northbound"]:
            msgs.append(f"北向资金: {result['northbound']}")

        if result["errors"]:
            msgs.append(f"错误: {'; '.join(result['errors'])}")

        self._log(" | ".join(msgs))
        self._log("===== 抓取完成 =====")
        self.status.setText(" | ".join(msgs))
        self._refresh()

    def _show_msg(self, layout, msg: str):
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        layout.addWidget(label)
