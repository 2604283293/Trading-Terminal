from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date as DateType, datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select

from shared.data_sources import ActionItem, JiuyangongsheSource
from shared.storage.db import get_session
from shared.storage.models import ActionItemORM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("shared-api.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("shared.api")

SOURCES = {
    "jiuyangongshe": JiuyangongsheSource(),
}


def _upsert(items: list[ActionItem]) -> int:
    with get_session() as session:
        for item in items:
            existing = session.execute(
                select(ActionItemORM).where(
                    ActionItemORM.date == item.date,
                    ActionItemORM.source == item.source,
                    ActionItemORM.theme == item.theme,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.theme_id = item.theme_id
                existing.stock_count = item.stock_count
                existing.summary = item.summary
                existing.fetched_at = datetime.utcnow()
            else:
                session.add(
                    ActionItemORM(
                        date=item.date,
                        source=item.source,
                        theme=item.theme,
                        theme_id=item.theme_id,
                        stock_count=item.stock_count,
                        summary=item.summary,
                    )
                )
        session.commit()
        return len(items)


def _scrape_today_all_sources() -> None:
    today = DateType.today()
    for name, src in SOURCES.items():
        try:
            items = src.fetch(today)
            count = _upsert(items)
            log.info("scrape ok: source=%s date=%s items=%d", name, today, count)
        except Exception:
            log.exception("scrape failed: source=%s date=%s", name, today)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(_scrape_today_all_sources, CronTrigger(hour=12, minute=10), id="noon")
    scheduler.add_job(_scrape_today_all_sources, CronTrigger(hour=15, minute=40), id="close")
    scheduler.start()
    log.info("scheduler started; next runs: 12:10 / 15:40 Asia/Shanghai")
    yield
    scheduler.shutdown()


app = FastAPI(title="Trading Terminal Data Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "sources": list(SOURCES.keys())}


@app.get("/actions")
def list_actions(
    date: Optional[DateType] = Query(default=None, description="YYYY-MM-DD; 默认今天"),
    source: Optional[str] = Query(default=None, description="数据源标识；不传则返回全部"),
):
    target = date or DateType.today()
    with get_session() as session:
        stmt = select(ActionItemORM).where(ActionItemORM.date == target)
        if source:
            stmt = stmt.where(ActionItemORM.source == source)
        stmt = stmt.order_by(ActionItemORM.stock_count.desc(), ActionItemORM.theme)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "date": r.date.isoformat(),
                "source": r.source,
                "theme": r.theme,
                "theme_id": r.theme_id,
                "stock_count": r.stock_count,
                "summary": r.summary,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in rows
        ]


@app.post("/actions/scrape")
def trigger_scrape(
    date: Optional[DateType] = Query(default=None),
    source: Optional[str] = Query(default=None),
):
    target = date or DateType.today()
    if source and source not in SOURCES:
        raise HTTPException(status_code=400, detail=f"unknown source: {source}")
    targets = [SOURCES[source]] if source else list(SOURCES.values())

    total = 0
    errors: list[str] = []
    for src in targets:
        try:
            items = src.fetch(target)
            _upsert(items)
            total += len(items)
        except Exception as e:
            errors.append(f"{src.name}: {e}")
            log.exception("scrape failed: source=%s", src.name)

    return {
        "date": target.isoformat(),
        "scraped": total,
        "errors": errors,
    }
