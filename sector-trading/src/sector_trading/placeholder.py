"""板块交易 — 多源数据聚合：韭菜公社 + 东方财富(龙虎榜/北向/板块资金) + 灵启数据 API。"""
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
    load_dragon_tiger,
    load_dragon_tiger_seats,
    load_hot_rank,
    load_northbound,
    load_sector_flow,
    load_stocks,
    save_actions,
    save_billboard,
    save_northbound,
    save_sector_flow,
    save_stocks,
    load_finance,
    load_limit_list,
    load_etf_daily,
    load_auction,
)
from shared.noise_filter import CleanStock, CleanTheme, clean_today
from desktop_shell.theme import UP, DOWN, WARN, INFO, MUTED, DIM, CARD_BG, CARD_BORDER, SURFACE_BG


def _fmt_amt(v: float) -> str:
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.0f}"


def _pct_color(v: float) -> str:
    if v > 0:
        return UP
    elif v < 0:
        return DOWN
    return MUTED


# ── worker ──────────────────────────────────────────────────────

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

_STEP_TIMEOUT = 120  # 单个步骤最长等待秒数


def _run_with_timeout(fn, timeout: int = _STEP_TIMEOUT):
    """在线程池中执行 fn，超时则抛异常。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        return future.result(timeout=timeout)


class _ScrapeWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)

    def __init__(self, target_date: DateType):
        super().__init__()
        self._target = target_date

    def run(self) -> None:
        result = {"ok": True, "actions": 0, "stocks": 0, "billboard": 0,
                  "northbound": 0, "sector_flow": 0,
                  "daily_dump": 0, "hot_rank": 0, "dragon_tiger_api": 0,
                  "dragon_tiger_seats": 0,
                  "finance": 0, "limit_list": 0, "etf_daily": 0, "auction": 0,
                  "errors": []}

        # ── 东方财富数据 ──
        self.progress.emit("[东方财富] 获取龙虎榜/北向/板块资金…")
        try:
            def _do_em():
                from shared.data_pipeline import fetch_all as fetch_em
                return fetch_em(self._target)

            em = _run_with_timeout(_do_em, timeout=90)
            result["billboard"] = len(em.billboard)
            result["northbound"] = len(em.northbound)
            result["sector_flow"] = len(em.sector_flow)
            result["errors"].extend(em.errors)
            self.progress.emit(f"[东方财富] 完成: 龙虎榜{result['billboard']}, 北向{result['northbound']}, 板块{result['sector_flow']}")
        except FutureTimeout:
            msg = "东方财富: 超时 (90s), 已跳过"
            result["errors"].append(msg)
            self.progress.emit(msg)
        except Exception as exc:
            msg = f"东方财富: {exc}"
            result["errors"].append(msg)
            self.progress.emit(msg)

        # ── 灵启数据 API ──
        self.progress.emit("[API] 下载全市场日线/热度榜/龙虎榜…")
        try:
            def _do_api():
                from shared.data_pipeline import fetch_api_data
                return fetch_api_data(self._target)

            api = _run_with_timeout(_do_api, timeout=180)
            result["daily_dump"] = api.daily_dump_rows
            result["hot_rank"] = api.hot_rank_rows
            result["dragon_tiger_api"] = api.dragon_tiger_rows
            result["dragon_tiger_seats"] = api.dragon_tiger_seats_rows
            result["finance"] = api.finance_rows
            result["limit_list"] = api.limit_list_rows
            result["etf_daily"] = api.etf_daily_rows
            result["auction"] = api.auction_rows
            result["errors"].extend(api.errors)
            self.progress.emit(f"[API] 完成: 日线{result['daily_dump']}, 热度{result['hot_rank']}, 龙虎榜{result['dragon_tiger_api']}, 席位{result['dragon_tiger_seats']}, 涨跌停{result['limit_list']}, 财务{result['finance']}, ETF{result['etf_daily']}")
        except FutureTimeout:
            msg = "API数据: 超时 (180s), 已跳过"
            result["errors"].append(msg)
            self.progress.emit(msg)
        except Exception as exc:
            msg = f"API数据: {exc}"
            result["errors"].append(msg)
            self.progress.emit(msg)

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
                "QPushButton:disabled { background: #555; }"
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
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        toolbar.addWidget(self.status)

        self.scrape_btn = QPushButton("刷新全部数据")
        self.scrape_btn.setStyleSheet(
            "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background: #c13030; }"
            "QPushButton:disabled { background: #555; }"
        )
        self.scrape_btn.clicked.connect(self._scrape)
        toolbar.addWidget(self.scrape_btn)
        layout.addLayout(toolbar)

        # ── 子 tab ──
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._theme_content = self._make_scroll_area()
        self._billboard_content = self._make_scroll_area()
        self._hot_rank_content = self._make_scroll_area()
        self._dragon_tiger_content = self._make_scroll_area()
        self._sector_content = self._make_scroll_area()
        self._northbound_content = self._make_scroll_area()
        self._signal_content = self._make_scroll_area()
        self._limit_list_content = self._make_scroll_area()
        self._etf_daily_content = self._make_scroll_area()
        self._finance_content = self._make_scroll_area()
        self._auction_content = self._make_scroll_area()

        self._tabs.addTab(self._theme_content, "异动主题")
        self._tabs.addTab(self._billboard_content, "龙虎榜(东财)")
        self._tabs.addTab(self._hot_rank_content, "同花顺热度")
        self._tabs.addTab(self._dragon_tiger_content, "龙虎榜(API)")
        self._tabs.addTab(self._sector_content, "板块资金")
        self._tabs.addTab(self._northbound_content, "北向资金")
        self._tabs.addTab(self._signal_content, "综合信号")
        self._tabs.addTab(self._limit_list_content, "涨跌停")
        self._tabs.addTab(self._etf_daily_content, "ETF行情")
        self._tabs.addTab(self._finance_content, "财务指标")
        self._tabs.addTab(self._auction_content, "集合竞价")

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
            "QPushButton { padding: 2px 8px; border: 1px solid #3a3a3a; border-radius: 2px; color: #888; }"
            "QPushButton:hover { color: #ccc; border-color: #999; }"
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
        self._refresh_hot_rank(today)
        self._refresh_dragon_tiger_api(today)
        self._refresh_sector_flow(today)
        self._refresh_northbound(today)
        self._refresh_signals(today)
        self._refresh_limit_list(today)
        self._refresh_etf_daily(today)
        self._refresh_finance(today)
        self._refresh_auction(today)

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

        self._tabs.setTabText(1, f"龙虎榜(东财) ({len(df)})")

        # 按主力净买入排序
        df = df.sort_values("net_buy", ascending=False)

        for _, row in df.iterrows():
            layout.addWidget(self._make_billboard_card(row))

    def _refresh_hot_rank(self, today: DateType):
        self._clear_tab(self._hot_rank_content)
        layout = self._hot_rank_content.content_layout

        df = load_hot_rank(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无同花顺热度数据。点击『刷新全部数据』抓取。")
            return

        self._tabs.setTabText(2, f"同花顺热度 ({len(df)})")

        # 按排名排序
        df = df.sort_values("rank")
        for _, row in df.iterrows():
            layout.addWidget(self._make_hot_rank_card(row))

    def _refresh_dragon_tiger_api(self, today: DateType):
        self._clear_tab(self._dragon_tiger_content)
        layout = self._dragon_tiger_content.content_layout

        df = load_dragon_tiger(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无龙虎榜(API)数据。点击『刷新全部数据』抓取。")
            return

        # 加载席位明细
        seats_df = load_dragon_tiger_seats(today)
        seats_by_code: dict[str, pd.DataFrame] = {}
        if len(seats_df) > 0:
            for code, grp in seats_df.groupby("stock_code"):
                seats_by_code[code] = grp.sort_values("net_buy_amount", ascending=False)

        n_stocks = len(df)
        n_seats = len(seats_df)
        label = f"龙虎榜(API) ({n_stocks}只"
        if n_seats:
            label += f", {n_seats}席位"
        label += ")"
        self._tabs.setTabText(3, label)

        # 按净买入排序
        if "net_amount" in df.columns:
            df = df.sort_values("net_amount", ascending=False)

        for _, row in df.iterrows():
            code = row.get("stock_code", "")
            stock_seats = seats_by_code.get(code)
            layout.addWidget(self._make_dragon_tiger_card(row, stock_seats))

    def _refresh_sector_flow(self, today: DateType):
        self._clear_tab(self._sector_content)
        layout = self._sector_content.content_layout

        df = load_sector_flow(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无板块资金流数据。")
            return

        self._tabs.setTabText(4, f"板块资金 ({len(df)})")

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

        self._tabs.setTabText(5, f"北向资金 {sign}")

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

        self._tabs.setTabText(6, f"综合信号 ({len(stocks)})")
        self._log(f"综合信号: {len(themes)} 个清洗主题, {len(stocks)} 只评分个股")

        # ── 主题摘要 ──
        main_line = [t for t in themes if t.quality == "main_line"]
        hot = [t for t in themes if t.quality == "hot"]
        new = [t for t in themes if t.quality == "new"]

        summary_text = f"主线 {len(main_line)} 个 · 热点 {len(hot)} 个 · 新题材 {len(new)} 个"
        summary = QLabel(summary_text)
        summary.setStyleSheet("font-size: 13px; color: #aaa; padding: 4px 0 8px 0;")
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
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
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
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
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
            name_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #ccc;")
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
            vol_lbl.setStyleSheet("font-size: 12px; color: #aaa;")
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
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 12px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        header = QHBoxLayout()
        theme = QLabel(item["theme"])
        theme.setStyleSheet("font-size: 16px; font-weight: bold; color: #ddd;")
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
            summary.setStyleSheet("color: #bbb; font-size: 13px;")
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
                style = "font-size: 12px; color: #ccc;"
                if key == "name":
                    style = "font-size: 12px; font-weight: bold; color: #ccc;"
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
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        # 第一行：名称 + 代码 + 涨跌幅
        h1 = QHBoxLayout()
        name = QLabel(f"{row['name']}  {row['code']}")
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
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
            reason.setStyleSheet("font-size: 11px; color: #999; background: #252525; "
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
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
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
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
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

    def _make_hot_rank_card(self, row) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 8px 12px; }"
        )
        layout = QHBoxLayout(card)
        layout.setSpacing(12)

        # 排名徽章
        rank = int(row["rank"]) if row.get("rank") else 0
        rank_color = "#d83a3a" if rank <= 3 else ("#e8870a" if rank <= 10 else "#888")
        rank_lbl = QLabel(str(rank))
        rank_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: #fff; background: {rank_color}; "
            "min-width: 28px; min-height: 28px; border-radius: 14px; "
            "qproperty-alignment: AlignCenter;"
        )
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rank_lbl.setFixedSize(28, 28)
        layout.addWidget(rank_lbl)

        # 名称 + 代码
        name_text = f"{row['name']}  <span style='color:#888;font-size:11px;'>{row['code']}</span>"
        name = QLabel(name_text)
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
        name.setFixedWidth(260)
        layout.addWidget(name)

        # 涨跌幅
        pct = float(row.get("pct_change", 0) or 0)
        chg = QLabel(f"{pct:+.2f}%")
        chg.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_pct_color(pct)};")
        chg.setFixedWidth(80)
        layout.addWidget(chg)

        # 热度值
        hot = float(row.get("hot", 0) or 0)
        hot_lbl = QLabel(f"热度: {hot:.1f}")
        hot_lbl.setStyleSheet("font-size: 12px; color: #e8870a; font-weight: bold;")
        layout.addWidget(hot_lbl)

        # 市场标签
        market = row.get("market", "")
        if market:
            mkt_tag = QLabel(market)
            mkt_tag.setStyleSheet(
                "font-size: 10px; color: #2e7fd8; background: #e8f0fe; "
                "padding: 2px 6px; border-radius: 3px;"
            )
            layout.addWidget(mkt_tag)

        layout.addStretch()
        return card

    def _make_dragon_tiger_card(self, row, seats=None) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #2b2b2b; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        # 第一行：名称 + 代码 + 涨跌幅
        h1 = QHBoxLayout()
        name_text = f"{row.get('name', '')}  {row['stock_code']}"
        name = QLabel(name_text)
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ddd;")
        h1.addWidget(name)
        h1.addStretch()
        pct = float(row.get("pct_change", 0) or 0)
        chg = QLabel(f"{pct:+.2f}%")
        chg.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {_pct_color(pct)};")
        h1.addWidget(chg)
        layout.addLayout(h1)

        # 第二行：净买入 + 成交额占比
        h2 = QHBoxLayout()
        net = float(row.get("net_amount", 0) or 0)
        net_label = QLabel(f"龙虎榜净买入: {_fmt_amt(net * 10000)}")
        net_label.setStyleSheet(f"font-size: 12px; color: {_pct_color(net)}; font-weight: bold;")
        h2.addWidget(net_label)
        rate = float(row.get("net_rate", 0) or 0)
        rate_label = QLabel(f"净买占比: {rate:.1f}%")
        rate_label.setStyleSheet("font-size: 12px; color: #888;")
        h2.addWidget(rate_label)
        amt_rate = float(row.get("amount_rate", 0) or 0)
        amt_label = QLabel(f"成交占比: {amt_rate:.1f}%")
        amt_label.setStyleSheet("font-size: 12px; color: #888;")
        h2.addWidget(amt_label)
        h2.addStretch()
        layout.addLayout(h2)

        # 第三行：买卖额 + 原因
        h3 = QHBoxLayout()
        l_buy = float(row.get("l_buy", 0) or 0)
        l_sell = float(row.get("l_sell", 0) or 0)
        detail = QLabel(f"买入: {_fmt_amt(l_buy * 10000)}  |  卖出: {_fmt_amt(l_sell * 10000)}")
        detail.setStyleSheet("font-size: 11px; color: #999;")
        h3.addWidget(detail)
        h3.addStretch()
        reason = row.get("reason", "")
        if reason:
            reason_lbl = QLabel(str(reason))
            reason_lbl.setStyleSheet(
                "font-size: 10px; color: #999; background: #252525; "
                "padding: 2px 6px; border-radius: 3px;"
            )
            h3.addWidget(reason_lbl)
        layout.addLayout(h3)

        # 第四部分：席位买卖明细
        if seats is not None and len(seats) > 0:
            sep = QLabel("席位买卖明细")
            sep.setStyleSheet("font-size: 11px; color: #d83a3a; font-weight: bold; "
                            "border-top: 1px solid #f0f0f0; padding-top: 6px; margin-top: 4px;")
            layout.addWidget(sep)

            for _, s in seats.iterrows():
                seat_row = QHBoxLayout()
                seat_row.setSpacing(8)

                org = QLabel(str(s.get("org_name", "")))
                org.setStyleSheet("font-size: 11px; color: #bbb;")
                org.setFixedWidth(260)
                seat_row.addWidget(org)

                buy = float(s.get("buy_amount", 0) or 0)
                buy_lbl = QLabel(f"买 {_fmt_amt(buy)}")
                buy_lbl.setStyleSheet("font-size: 11px; color: #d83a3a; font-weight: bold;")
                buy_lbl.setFixedWidth(80)
                seat_row.addWidget(buy_lbl)

                sell = float(s.get("sell_amount", 0) or 0)
                sell_lbl = QLabel(f"卖 {_fmt_amt(sell)}")
                sell_lbl.setStyleSheet("font-size: 11px; color: #2e9f3e; font-weight: bold;")
                sell_lbl.setFixedWidth(80)
                seat_row.addWidget(sell_lbl)

                net_s = float(s.get("net_buy_amount", 0) or 0)
                net_color = "#d83a3a" if net_s >= 0 else "#2e9f3e"
                net_lbl = QLabel(f"净 {_fmt_amt(abs(net_s))}")
                net_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {net_color};")
                seat_row.addWidget(net_lbl)

                seat_row.addStretch()
                layout.addLayout(seat_row)

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
        worker.progress.connect(lambda msg: (self.status.setText(msg), self._log(msg)))
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
            msgs.append(f"龙虎榜(东财): {result['billboard']}")
        if result["daily_dump"]:
            msgs.append(f"全市场日线: {result['daily_dump']}")
        if result["hot_rank"]:
            msgs.append(f"同花顺热度: {result['hot_rank']}")
        if result["dragon_tiger_api"]:
            msgs.append(f"龙虎榜(API): {result['dragon_tiger_api']}")
        if result["dragon_tiger_seats"]:
            msgs.append(f"席位明细: {result['dragon_tiger_seats']}")
        if result["sector_flow"]:
            msgs.append(f"板块资金: {result['sector_flow']}")
        if result["northbound"]:
            msgs.append(f"北向资金: {result['northbound']}")
        if result["limit_list"]:
            msgs.append(f"涨跌停: {result['limit_list']}")
        if result["finance"]:
            msgs.append(f"财务指标: {result['finance']}")
        if result["etf_daily"]:
            msgs.append(f"ETF行情: {result['etf_daily']}")
        if result["auction"]:
            msgs.append(f"集合竞价: {result['auction']}")

        if result["errors"]:
            msgs.append(f"错误: {'; '.join(result['errors'])}")

        self._log(" | ".join(msgs))
        self._log("===== 抓取完成 =====")
        self.status.setText(" | ".join(msgs))
        self._refresh()

    # ── 涨跌停 ──────────────────────────────────────────────────

    def _refresh_limit_list(self, today: DateType):
        self._clear_tab(self._limit_list_content)
        layout = self._limit_list_content.content_layout

        df = load_limit_list(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无涨跌停数据。点击『刷新全部数据』抓取。")
            return

        up_count = len(df[df["limit"] == "U"]) if "limit" in df.columns else 0
        down_count = len(df[df["limit"] == "D"]) if "limit" in df.columns else 0
        self._tabs.setTabText(7, f"涨跌停 ({up_count}涨停/{down_count}跌停)")

        # 按成交额排序
        if "amount" in df.columns:
            df = df.sort_values("amount", ascending=False)

        for _, row in df.iterrows():
            layout.addWidget(self._make_limit_card(row))

    def _make_limit_card(self, row) -> QWidget:
        limit_val = row.get("limit", "")
        if limit_val == "U":
            badge = '<span style="color:#fff; background:#d83a3a; padding:2px 6px; border-radius:3px; font-size:11px;">涨停</span>'
        elif limit_val == "D":
            badge = '<span style="color:#fff; background:#2e9f3e; padding:2px 6px; border-radius:3px; font-size:11px;">跌停</span>'
        elif limit_val == "Z":
            badge = '<span style="color:#fff; background:#f0a020; padding:2px 6px; border-radius:3px; font-size:11px;">炸板</span>'
        else:
            badge = '<span style="color:#888;">--</span>'

        name = row.get("name", row.get("stock_code", ""))
        code = row.get("stock_code", "")
        industry = row.get("industry", "")
        close = row.get("close", 0)
        pct = row.get("pct_chg", 0) or 0
        amount = row.get("amount", 0) or 0
        limit_amt = row.get("limit_amount", 0) or 0
        turnover = row.get("turnover_ratio", 0) or 0
        float_mv = row.get("float_mv", 0) or 0
        fd_amt = row.get("fd_amount", 0) or 0
        open_times = row.get("open_times", 0) or 0
        limit_times = row.get("limit_times", 0) or 0

        pct_str = f"{pct:+.2f}%" if pct else "0%"
        pct_color = _pct_color(pct)

        text = (
            f"<div style='padding: 8px 12px; border: 1px solid #3a3a3a; border-radius: 6px; background: #2b2b2b;'>"
            f"<div style='display: flex; justify-content: space-between; align-items: center;'>"
            f"<span style='font-weight: bold; font-size: 14px;'>{name} <span style='color:#888; font-size:11px;'>{code}</span></span>"
            f"{badge}"
            f"</div>"
            f"<div style='margin-top: 6px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #999;'>"
            f"<span>收盘: {close:.2f}</span>"
            f"<span style='color:{pct_color}; font-weight:bold;'>{pct_str}</span>"
            f"<span>成交额: {_fmt_amt(amount)}</span>"
            f"<span>封单额: {_fmt_amt(fd_amt)}</span>"
            f"</div>"
            f"<div style='margin-top: 4px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: #999;'>"
            f"<span>流通市值: {_fmt_amt(float_mv)}</span>"
            f"<span>换手率: {turnover:.2f}%</span>"
        )
        if open_times > 0:
            text += f"<span>开板: {int(open_times)}次</span>"
        if limit_times > 1:
            text += f"<span style='color:#d83a3a;'>{int(limit_times)}连板</span>"
        if industry:
            text += f"<span>行业: {industry}</span>"
        text += "</div></div>"

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("QLabel { padding: 0; }")
        return lbl

    # ── ETF 行情 ─────────────────────────────────────────────────

    def _refresh_etf_daily(self, today: DateType):
        self._clear_tab(self._etf_daily_content)
        layout = self._etf_daily_content.content_layout

        df = load_etf_daily(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无 ETF 数据。点击『刷新全部数据』抓取。")
            return

        self._tabs.setTabText(8, f"ETF行情 ({len(df)})")

        if "pct_chg" in df.columns:
            df = df.sort_values("pct_chg", ascending=False)

        for _, row in df.iterrows():
            layout.addWidget(self._make_etf_card(row))

    def _make_etf_card(self, row) -> QWidget:
        code = row.get("stock_code", "")
        close = row.get("close", 0) or 0
        pct = row.get("pct_chg", 0) or 0
        amount = row.get("amount", 0) or 0
        volume = row.get("volume", 0) or 0
        total_assets = row.get("total_assets", 0) or 0
        unit_nav = row.get("unit_nav", 0) or 0
        accum_nav = row.get("accum_nav", 0) or 0
        iopv = row.get("iopv", 0) or 0

        pct_str = f"{pct:+.2f}%" if pct else "0%"
        pct_color = _pct_color(pct)

        text = (
            f"<div style='padding: 8px 12px; border: 1px solid #3a3a3a; border-radius: 6px; background: #2b2b2b;'>"
            f"<div style='display: flex; justify-content: space-between; align-items: center;'>"
            f"<span style='font-weight: bold; font-size: 13px;'>{code}</span>"
            f"<span style='font-weight: bold; color:{pct_color}; font-size: 14px;'>{pct_str}</span>"
            f"</div>"
            f"<div style='margin-top: 4px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #999;'>"
            f"<span>收盘: {close:.4f}</span>"
            f"<span>成交额: {_fmt_amt(amount)}</span>"
        )
        if total_assets:
            text += f"<span>规模: {_fmt_amt(total_assets * 10000)}</span>"
        if unit_nav:
            text += f"<span>单位净值: {unit_nav:.4f}</span>"
        if iopv:
            text += f"<span>IOPV: {iopv:.4f}</span>"
        text += "</div></div>"

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("QLabel { padding: 0; }")
        return lbl

    # ── 财务指标 ─────────────────────────────────────────────────

    def _refresh_finance(self, today: DateType):
        self._clear_tab(self._finance_content)
        layout = self._finance_content.content_layout

        df = load_finance(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无财务指标数据。点击『刷新全部数据』抓取。")
            return

        self._tabs.setTabText(9, f"财务指标 ({len(df)})")

        # 按换手率降序
        if "turnover_rate" in df.columns:
            df = df.sort_values("turnover_rate", ascending=False)

        # 显示前200条（数据量大）
        shown = 0
        for _, row in df.iterrows():
            if shown >= 200:
                break
            layout.addWidget(self._make_finance_card(row))
            shown += 1
        if len(df) > 200:
            more = QLabel(f"…… 还有 {len(df) - 200} 条，仅显示换手率最高的前 200 只")
            more.setAlignment(Qt.AlignmentFlag.AlignCenter)
            more.setStyleSheet("color: #888; padding: 8px; font-size: 12px;")
            layout.addWidget(more)

    def _make_finance_card(self, row) -> QWidget:
        code = row.get("stock_code", "")
        close = row.get("close", 0) or 0
        pe = row.get("pe", 0) or 0
        pb = row.get("pb", 0) or 0
        turnover = row.get("turnover_rate", 0) or 0

        pe_str = f"PE: {pe:.1f}" if pe > 0 else "PE: --"
        pb_str = f"PB: {pb:.2f}" if pb > 0 else "PB: --"

        text = (
            f"<div style='padding: 6px 12px; border: 1px solid #3a3a3a; border-radius: 4px; background: #2b2b2b;'>"
            f"<span style='font-weight: bold; font-size: 12px;'>{code}</span>"
            f"<span style='margin-left: 12px; font-size: 12px; color: #999;'>{pe_str}</span>"
            f"<span style='margin-left: 12px; font-size: 12px; color: #999;'>{pb_str}</span>"
            f"<span style='margin-left: 12px; font-size: 12px; color: #999;'>换手: {turnover:.2f}%</span>"
            f"<span style='margin-left: 12px; font-size: 12px; color: #999;'>收盘: {close:.2f}</span>"
            f"</div>"
        )

        lbl = QLabel(text)
        lbl.setWordWrap(False)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("QLabel { padding: 0; }")
        return lbl

    # ── 集合竞价 ─────────────────────────────────────────────────

    def _refresh_auction(self, today: DateType):
        self._clear_tab(self._auction_content)
        layout = self._auction_content.content_layout

        df = load_auction(today)
        if len(df) == 0:
            self._show_msg(layout, "暂无集合竞价数据。（仅当天 9:15-9:25 可获取）")
            return

        self._tabs.setTabText(10, f"集合竞价 ({len(df)})")

        # 按成交额降序
        if "amount" in df.columns:
            df = df.sort_values("amount", ascending=False)

        for _, row in df.iterrows():
            layout.addWidget(self._make_auction_card(row))

    def _make_auction_card(self, row) -> QWidget:
        code = row.get("stock_code", "")
        name = row.get("stock_name", "")
        close = row.get("close", 0) or 0
        pre_close = row.get("pre_close", 0) or 0
        vol = row.get("vol", 0) or 0
        amount = row.get("amount", 0) or 0
        turnover = row.get("turnover_rate", 0) or 0
        ask_price = row.get("ask_price", 0) or 0
        bid_price = row.get("bid_price", 0) or 0
        ask_vol = row.get("ask_vol", 0) or 0
        bid_vol = row.get("bid_vol", 0) or 0

        pct = ((close - pre_close) / pre_close * 100) if pre_close else 0
        pct_str = f"{pct:+.2f}%" if pre_close else "--"
        pct_color = _pct_color(pct)

        text = (
            f"<div style='padding: 8px 12px; border: 1px solid #3a3a3a; border-radius: 6px; background: #2b2b2b;'>"
            f"<div style='display: flex; justify-content: space-between; align-items: center;'>"
            f"<span style='font-weight: bold; font-size: 13px;'>{name} <span style='color:#888; font-size:11px;'>{code}</span></span>"
            f"<span style='font-weight: bold; color:{pct_color}; font-size: 14px;'>{pct_str}</span>"
            f"</div>"
            f"<div style='margin-top: 4px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #999;'>"
            f"<span>当前价: {close:.2f}</span>"
            f"<span>昨收: {pre_close:.2f}</span>"
            f"<span>成交额: {_fmt_amt(amount)}</span>"
            f"<span>成交量: {int(vol):,}</span>"
            f"</div>"
            f"<div style='margin-top: 3px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: #999;'>"
            f"<span style='color:#d83a3a;'>卖一: {ask_price:.2f} ({int(ask_vol):,})</span>"
            f"<span style='color:#2e9f3e;'>买一: {bid_price:.2f} ({int(bid_vol):,})</span>"
        )
        if turnover:
            text += f"<span>换手: {turnover:.2f}%</span>"
        text += "</div></div>"

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("QLabel { padding: 0; }")
        return lbl

    def _show_msg(self, layout, msg: str):
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #888; padding: 40px; font-size: 13px;")
        layout.addWidget(label)
