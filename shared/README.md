# 共享数据服务 (shared)

聚合 TDX 盘后文件、Tushare、AkShare 等数据源，对外提供统一 REST API。

详见根目录 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 职责
- 每日 17:00 定时拉取 / 解析数据
- 历史 K 线缓存（Parquet）
- 板块/概念/资讯缓存（SQLite）
- 对客户端提供 FastAPI 接口

## 技术栈
- FastAPI + uvicorn
- mootdx（TDX 盘后文件解析）
- Tushare Pro（板块/财务）
- AkShare + RSS（资讯）
- APScheduler（定时任务）
- SQLAlchemy + SQLite + Parquet
