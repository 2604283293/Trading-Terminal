"""韭研公社 异动解析 — Selenium 版完整抓取。

抓取两层数据：
1. 主题摘要（与 selectolax 版相同）
2. 个股明细（点击展开后解析每个主题下的股票列表）

输出到本地 Parquet，UI 直接读取。
"""
from __future__ import annotations

import time
from datetime import date as DateType

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions

BASE_URL = "https://www.jiuyangongshe.com/action"


def _build_driver() -> webdriver.Edge:
    opts = EdgeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Edge(options=opts)


def fetch_all(target_date: DateType) -> dict:
    """抓取指定日期的所有异动数据。

    Returns:
        {"actions": [{theme summary}], "stocks": [{stock detail}]}
    """
    url = f"{BASE_URL}/{target_date.isoformat()}"
    driver = None
    try:
        driver = _build_driver()
        driver.get(url)
        time.sleep(3)

        # 点击展开全部详情
        try:
            driver.find_element(By.CLASS_NAME, "action-main").click()
            time.sleep(2)
        except Exception:
            pass

        page = driver.page_source
        return _parse_page(page, target_date)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _parse_page(html: str, target_date: DateType) -> dict:
    soup = BeautifulSoup(html, "lxml")
    box = soup.find("ul", class_="module-box")
    if box is None:
        return {"actions": [], "stocks": []}

    date_str = target_date.isoformat()
    cards = box.find_all("li", class_="module")

    actions: list[dict] = []
    stocks: list[dict] = []

    for card in cards:
        # --- 主题头 ---
        name_el = card.find(class_="fs18-bold")
        theme_name = name_el.text.strip() if name_el else ""

        count_el = card.find(class_="number")
        try:
            stock_count = int(count_el.text.strip() or "0")
        except (AttributeError, ValueError):
            stock_count = 0

        summary_el = card.find(class_="mtb8")
        summary = ""
        if summary_el:
            summary = summary_el.text.strip().removeprefix("题材：").strip()

        theme_id = ""
        id_el = card.find("div", class_="hsh-flex-upDown")
        if id_el:
            theme_id = id_el.get("id", "") or ""

        actions.append({
            "date": date_str,
            "source": "jiuyangongshe",
            "theme": theme_name,
            "theme_id": theme_id,
            "stock_count": stock_count,
            "summary": summary,
        })

        # --- 个股列表 ---
        stock_table = card.find("ul", class_="td-box")
        if stock_table is None:
            continue

        for row in stock_table.find_all("li"):
            try:
                sec_name = ""
                sec_name_el = row.find("div", class_="shrink")
                if sec_name_el:
                    sec_name = sec_name_el.text.strip()

                sec_code = ""
                sec_code_el = row.find("div", class_="force-wrap")
                if sec_code_el:
                    raw = sec_code_el.text.strip()
                    sec_code = raw.replace("sz", "").replace("sh", "").replace("bj", "")

                last_price = ""
                price_el = row.find("div", class_="number")
                if price_el:
                    last_price = price_el.text.strip()

                change_pct = ""
                tg_el = row.find("div", class_="cred")
                if tg_el is None:
                    tg_el = row.find("div", class_="cgreen")
                if tg_el:
                    change_pct = tg_el.text.strip()

                limit_time = ""
                time_el = row.find("div", class_="fs15")
                if time_el:
                    limit_time = time_el.text.strip()

                action_type = ""
                action_el = row.find("div", class_="sort")
                if action_el:
                    action_type = action_el.text.strip()

                analysis = ""
                ays_el = row.find("pre", class_="pre")
                if ays_el:
                    analysis = ays_el.text.strip()

                stock_summary = ""
                if analysis:
                    lines = analysis.split("\n")
                    if lines:
                        stock_summary = lines[0].strip()

                stocks.append({
                    "date": date_str,
                    "source": "jiuyangongshe",
                    "theme": theme_name,
                    "code": sec_code,
                    "name": sec_name,
                    "action_type": action_type,
                    "summary": stock_summary,
                    "last_price": last_price,
                    "change_pct": change_pct,
                    "limit_time": limit_time,
                    "analysis": analysis,
                })
            except Exception:
                continue

    return {"actions": actions, "stocks": stocks}
