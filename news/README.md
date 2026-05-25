# 资讯模块 (News)

行情、新闻、公告等资讯展示模块。

详见根目录 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 技术栈
- PySide6（UI）
- SQLite FTS5（全文检索）
- 数据通过共享数据服务（[`../shared/`](../shared)）获取，主要源 AkShare + RSS
