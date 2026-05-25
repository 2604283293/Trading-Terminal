# 图形交易模块 (Graphical Trading)

基于图表/图形界面的交易功能模块。

详见根目录 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 技术栈
- PySide6 + pyqtgraph（K 线图表）
- pandas + pandas-ta（指标计算）
- 数据通过共享数据服务（[`../shared/`](../shared)）按需获取
