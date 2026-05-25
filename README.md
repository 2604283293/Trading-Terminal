# Trading Terminal

交易终端项目，由多个相互独立的子模块组成，每个模块可独立开发与发布。

## 模块列表

| 目录 | 模块 | 说明 |
| --- | --- | --- |
| [`graphical-trading/`](./graphical-trading) | 图形交易模块 | 基于图表/图形界面的交易功能 |
| [`sector-trading/`](./sector-trading) | 板块交易模块 | 按板块维度进行交易与分析 |
| [`news/`](./news) | 资讯模块 | 行情、新闻、公告等资讯展示 |

后续可在根目录下新增独立模块文件夹进行扩展。

## 开发约定

- 每个模块在自己的目录内独立维护代码、依赖与文档
- 顶层仓库只放跨模块的共享配置和说明
- 各模块的提交建议在 commit message 中加前缀，例如：
  - `graphical:` / `sector:` / `news:`
