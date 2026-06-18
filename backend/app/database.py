"""Database engine, session factory, and ORM models."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import DATABASE_URL

# SQLite needs check_same_thread disabled because FastAPI serves sync endpoints
# from a threadpool.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Twin(Base):
    """An AI version of a person."""

    __tablename__ = "twins"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner: Mapped[str] = mapped_column(String(120), default="")
    tagline: Mapped[str] = mapped_column(String(280), default="")
    # The synthesized persona profile, stored as a JSON string. Empty until the
    # twin has been trained at least once.
    persona_json: Mapped[str] = mapped_column(Text, default="")
    persona_updated_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    samples: Mapped[list["TrainingSample"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", order_by="TrainingSample.id"
    )


class TrainingSample(Base):
    """A single piece of training data the twin learns from."""

    __tablename__ = "training_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    twin_id: Mapped[int] = mapped_column(ForeignKey("twins.id"))
    category: Mapped[str] = mapped_column(String(40))  # one of TRAINING_CATEGORIES
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    twin: Mapped[Twin] = relationship(back_populates="samples")


def init_db() -> None:
    Base.metadata.create_all(engine)
