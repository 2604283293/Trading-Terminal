"""韭研公社 异动解析 数据源。

主页结构（Nuxt SSR，数据直接在 HTML 里）：

    <ul class="module-box">
      <li class="module">
        <div id="<theme_id>" class="hsh-flex-upDown jc-bline">
          <div class="sort-box">
            <div class="count-filed">
              <div class="fs18-bold">机器人</div>
              <div class="number">13</div>
            </div>
            <div class="mtb8 text-justify">
              <span class="fs16-bold">题材：</span>
              发改委：将加快具身智能训练基础设施建设
            </div>
          </div>
        </div>
      </li>
      ...
    </ul>

URL：https://www.jiuyangongshe.com/action/{YYYY-MM-DD}
"""
from __future__ import annotations

from datetime import date as DateType

import httpx
from selectolax.parser import HTMLParser

from shared.data_sources.base import ActionItem

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class JiuyangongsheSource:
    name = "jiuyangongshe"
    base_url = "https://www.jiuyangongshe.com"

    def fetch(self, target_date: DateType) -> list[ActionItem]:
        url = f"{self.base_url}/action/{target_date.isoformat()}"
        with httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0),
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
        return self._parse(html, target_date)

    def _parse(self, html: str, target_date: DateType) -> list[ActionItem]:
        tree = HTMLParser(html)
        items: list[ActionItem] = []
        for card in tree.css("ul.module-box li.module"):
            name_node = card.css_first("div.count-filed div.fs18-bold")
            count_node = card.css_first("div.count-filed div.number")
            if name_node is None or count_node is None:
                continue

            theme_name = name_node.text(strip=True)
            try:
                stock_count = int(count_node.text(strip=True) or "0")
            except ValueError:
                stock_count = 0

            summary = ""
            summary_node = card.css_first("div.mtb8.text-justify")
            if summary_node is not None:
                summary = summary_node.text(strip=True).removeprefix("题材：").strip()

            theme_id = ""
            id_node = card.css_first("div.hsh-flex-upDown.jc-bline")
            if id_node is not None:
                theme_id = id_node.attributes.get("id", "") or ""

            items.append(
                ActionItem(
                    date=target_date,
                    source=self.name,
                    theme=theme_name,
                    theme_id=theme_id,
                    stock_count=stock_count,
                    summary=summary,
                )
            )
        return items
