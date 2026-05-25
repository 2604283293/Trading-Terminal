# Trading Terminal 架构与技术选型

> 决策日期：2026-05-25
> 修订记录见文末

## 1. 项目目标

为 8–10 个熟人用户提供 **A 股盘后分析与选股** 的桌面终端，包含三个独立可演进的业务模块：

- **图形交易**：K 线 + 指标 + 画线
- **板块交易**：板块分类、轮动、资金流
- **资讯**：新闻、公告、检索

不下单、不实时、个人/小团体使用。

## 2. 关键约束

| 约束 | 影响 |
|---|---|
| 仅 A 股 | 数据生态以 Python 为主，选 Python 技术栈契合度最高 |
| 桌面端 | 客户端本地化，分发体积/安装难度要可控 |
| 不下单 | 无资金风险，无需券商 API 集成、API key 安全存储 |
| 仅盘后 | 数据服务可单向拉取，无需 WebSocket，架构大幅简化 |
| 8–10 人 | 数据服务集中部署一份即可，Tushare 配额共享 |
| 模块独立开发 | monorepo 中每个模块独立 pyproject.toml，UI 上统一壳子组装 |

## 3. 总体架构

```
┌─────────────────────────────────────────────────────┐
│  共享数据服务 (shared/)                              │
│  FastAPI · 一台机器/家庭服务器即可                    │
│                                                     │
│  每日 17:00 APScheduler 定时任务：                    │
│    1. 触发通达信盘后下载（或读已下载文件）             │
│    2. mootdx 解析 .day/.lc5 → Parquet 缓存           │
│    3. Tushare Pro 增量拉取板块/概念/资金流/财务        │
│    4. AkShare + RSS 抓取资讯                          │
│                                                     │
│  REST 接口：GET /klines /sectors /news ...           │
└─────────────────────────────────────────────────────┘
                       ▲
                       │ HTTP/JSON（按需查询，无推送）
                       ▼
┌─────────────────────────────────────────────────────┐
│  桌面客户端 (desktop-shell/)                          │
│  PySide6 主程序 · 8–10 人各装一份                     │
│                                                     │
│  ┌─ Tab: 图形交易 (graphical-trading/)                │
│  ├─ Tab: 板块交易 (sector-trading/)                   │
│  └─ Tab: 资讯     (news/)                             │
└─────────────────────────────────────────────────────┘
```

## 4. 技术栈

### 4.1 语言与工具链
- **Python 3.11+**
- **uv** — 包管理与 workspace（比 pip/poetry 快一个数量级）
- **ruff** — lint + format（一个工具替代 black/isort/flake8）

### 4.2 数据服务 (shared/)
| 角色 | 选型 |
|---|---|
| Web 框架 | FastAPI + uvicorn |
| 模型/校验 | Pydantic v2 |
| ORM | SQLAlchemy 2.0 + SQLite |
| 列式存储 | Parquet + pyarrow（历史 K 线） |
| 定时任务 | APScheduler |
| HTTP 客户端 | httpx |

### 4.3 桌面客户端
| 角色 | 选型 |
|---|---|
| UI 框架 | PySide6（Qt 6 官方绑定，LGPL，商用友好） |
| 组件库 | PyQt-Fluent-Widgets |
| K 线图表 | pyqtgraph（主） / KLineChart via QtWebEngine（备） |
| 板块热力图 | ECharts via QtWebEngine（treemap 效果最佳） |
| 指标计算 | pandas + pandas-ta |
| 数据处理 | pandas + numpy |
| 打包分发 | Nuitka |

### 4.4 数据源分层

| 数据 | 源 | 选择理由 |
|---|---|---|
| 历史 K 线（日/周/月/分钟） | **TDX 盘后文件** + mootdx | 免费、海量、本地读取极快 |
| 板块/概念/资金流/财务 | **Tushare Pro**（200 元/年） | TDX 无法获取，Tushare 唯一可靠源 |
| 资讯/公告 | **AkShare** + RSS 自爬 | 免费、源最多 |

**禁用：** pytdx/mootdx 直连服务器实时模式 —— 仅盘后场景不需要实时数据，避免半官方协议风险。

## 5. 仓库结构

```
Trading-Terminal/
├── ARCHITECTURE.md          ← 本文档
├── README.md
├── pyproject.toml           ← uv workspace 根
├── .gitignore
│
├── shared/                  ← 共享数据服务（FastAPI）
│   ├── pyproject.toml
│   └── README.md
│
├── desktop-shell/           ← 桌面主程序壳子（PySide6 主入口）
│   ├── pyproject.toml
│   └── README.md
│
├── graphical-trading/       ← 图形交易模块
│   ├── pyproject.toml
│   └── README.md
│
├── sector-trading/          ← 板块交易模块
│   ├── pyproject.toml
│   └── README.md
│
└── news/                    ← 资讯模块
    ├── pyproject.toml
    └── README.md
```

**编码约定：**
- 每个模块在自己目录内独立维护代码与依赖
- 三个业务模块以 PySide6 Widget 形式由 desktop-shell 加载，不单独打包成可执行
- commit message 用模块前缀：`shared:` / `shell:` / `graphical:` / `sector:` / `news:`

## 6. 开发路线

### 阶段 1（1–2 周）：端到端最小闭环
1. `shared/`：FastAPI 起服务，mootdx 读一支股票日线，`GET /klines/{code}` 返回 JSON
2. `desktop-shell/`：PySide6 主窗口 + 三个 Tab 占位
3. `graphical-trading/`：pyqtgraph 画一支股票的 K 线

### 阶段 2：图形交易模块成形
- 多周期切换（日/周/月/分钟）
- 常用指标（MA / MACD / KDJ / BOLL）
- 选股结果联动

### 阶段 3：并行展开板块与资讯
- 板块模块：Tushare 板块清单 + 板块涨跌热力图 + 板块成员列表
- 资讯模块：AkShare/RSS 接入 + SQLite FTS5 全文检索

## 7. 关键决策记录

| 决策 | 时间 | 备选 | 选择理由 |
|---|---|---|---|
| Python 全栈 vs Tauri+React | 2026-05-25 | Tauri+React 客户端 + FastAPI 数据 | A 股生态 Python 最强；用户技术栈中立，单语言学习成本更低 |
| TDX 盘后 vs Tushare 主行情 | 2026-05-25 | 全 Tushare | TDX 盘后免费且本地极快，Tushare 仅用在它真正不可替代的板块/财务 |
| 不引入 pytdx 实时 | 2026-05-25 | pytdx/mootdx 直连实时 | 用户场景仅盘后，无实时需求；避免半官方协议风险 |
| FastAPI 集中数据服务 vs 客户端各自调 | 2026-05-25 | 每个客户端各自调 Tushare | 集中部署节省 Tushare 配额，缓存复用，新增模块易接入 |
| PySide6 vs PyQt6 | 2026-05-25 | PyQt6 | LGPL 商用友好，无授权风险 |
| 三模块统一壳子 vs 三个独立 EXE | 2026-05-25 | 三个独立可执行 | 8–10 人不想装三个图标；代码层面通过独立 pyproject.toml 保持解耦 |
