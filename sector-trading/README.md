# 板块交易模块 (Sector Trading)

按板块维度进行交易与分析的模块。

详见根目录 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 技术栈
- PySide6（UI）
- 板块热力图通过 QtWebEngine 嵌入 ECharts treemap
- 数据通过共享数据服务（[`../shared/`](../shared)）获取，主要源 Tushare Pro
