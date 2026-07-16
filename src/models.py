from __future__ import annotations

import json
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)  # substack / youtube / podcast
    url = Column(String(1024), nullable=False)
    rss_url = Column(String(1024))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    entries = relationship("Entry", back_populates="source", cascade="all, delete-orphan")


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    title = Column(String(1024), nullable=False)
    url = Column(String(2048), nullable=False)
    published_at = Column(DateTime)
    content_type = Column(String(50), nullable=False)  # article / video / podcast
    raw_text = Column(Text)
    audio_url = Column(String(2048))
    status = Column(String(50), default="pending")  # pending/transcribing/summarizing/done/failed
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="entries")
    summary = relationship("Summary", back_populates="entry", uselist=False, cascade="all, delete-orphan")
    bookmark = relationship("Bookmark", back_populates="entry", uselist=False, cascade="all, delete-orphan")


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("entries.id"), nullable=False, unique=True)
    thesis = Column(Text, nullable=False)
    key_points = Column(Text, nullable=False)  # JSON array
    conclusion = Column(Text, nullable=False)
    actionable_takeaways = Column(Text)  # JSON array
    tags = Column(Text)  # JSON array
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    entry = relationship("Entry", back_populates="summary")

    def get_key_points(self) -> list[dict]:
        return json.loads(self.key_points) if self.key_points else []

    def set_key_points(self, points: list[dict]):
        self.key_points = json.dumps(points, ensure_ascii=False)

    def get_actionable_takeaways(self) -> list[str]:
        return json.loads(self.actionable_takeaways) if self.actionable_takeaways else []

    def set_actionable_takeaways(self, takeaways: list[str]):
        self.actionable_takeaways = json.dumps(takeaways, ensure_ascii=False)

    def get_tags(self) -> list[str]:
        return json.loads(self.tags) if self.tags else []

    def set_tags(self, tag_list: list[str]):
        self.tags = json.dumps(tag_list, ensure_ascii=False)


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("entries.id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    entry = relationship("Entry", back_populates="bookmark")


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    digest_date = Column(Date, nullable=False, unique=True)
    entry_ids = Column(Text)  # JSON array of entry IDs
    email_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_entry_ids(self) -> list[int]:
        return json.loads(self.entry_ids) if self.entry_ids else []

    def set_entry_ids(self, ids: list[int]):
        self.entry_ids = json.dumps(ids)


class DailyQuestions(Base):
    """每日面试问题记录"""
    __tablename__ = "daily_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_date = Column(Date, nullable=False, unique=True)
    questions_json = Column(Text, nullable=False)  # JSON array of questions
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_questions(self) -> list[dict]:
        return json.loads(self.questions_json) if self.questions_json else []

    def set_questions(self, questions: list[dict]):
        self.questions_json = json.dumps(questions, ensure_ascii=False)


def get_engine():
    db_url = f"sqlite:///{settings.db_path}"
    return create_engine(db_url, echo=False)


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
