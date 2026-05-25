# Trading Terminal

A 股盘后分析桌面终端，多模块 monorepo（Python 全栈）。

详细架构与技术选型见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 模块

| 目录 | 模块 | 说明 |
| --- | --- | --- |
| [`shared/`](./shared) | 共享数据服务 | FastAPI 聚合 TDX / Tushare / AkShare |
| [`desktop-shell/`](./desktop-shell) | 桌面主程序壳子 | PySide6 主入口，承载三个业务模块 |
| [`graphical-trading/`](./graphical-trading) | 图形交易模块 | K 线 + 指标 + 画线 |
| [`sector-trading/`](./sector-trading) | 板块交易模块 | 板块涨跌、概念、资金流 |
| [`news/`](./news) | 资讯模块 | 新闻、公告、全文检索 |

## 开发

需要 Python 3.11+ 与 [uv](https://github.com/astral-sh/uv)。

```bash
# 同步根 workspace 所有模块依赖
uv sync

# 启动数据服务（待实现）
uv run --package tt-shared uvicorn shared.main:app --reload

# 启动桌面客户端（待实现）
uv run --package tt-desktop-shell python -m desktop_shell
```

## 约定

- 每个模块在自己目录内独立维护代码与依赖
- 三个业务模块以 PySide6 Widget 形式由 desktop-shell 加载
- commit message 前缀：`shared:` / `shell:` / `graphical:` / `sector:` / `news:`
- 不下单、仅盘后分析；不引入实时行情依赖
