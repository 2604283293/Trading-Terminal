from __future__ import annotations

from datetime import date as DateType, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ActionItemORM(Base):
    __tablename__ = "action_items"
    __table_args__ = (UniqueConstraint("date", "source", "theme", name="uq_date_source_theme"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[DateType] = mapped_column(Date, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(128), nullable=False)
    theme_id: Mapped[str] = mapped_column(String(64), default="")
    stock_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(String(2000), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
