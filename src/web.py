from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.models import Bookmark, DailyDigest, Entry, Source, Summary, get_session, init_db

app = FastAPI(title="Content Digest", version="0.1.0")

STATIC_DIR = Path(__file__).parent.parent / "static"


# --- Pydantic schemas ---

class SourceCreate(BaseModel):
    name: str
    platform: str
    url: str
    rss_url: Optional[str] = None


class SourceResponse(BaseModel):
    id: int
    name: str
    platform: str
    url: str
    rss_url: Optional[str]
    active: bool

    class Config:
        from_attributes = True


class KeyPoint(BaseModel):
    topic: Optional[str] = None
    speaker: Optional[str] = None
    text: str
    timestamp: Optional[str] = None


class SummaryResponse(BaseModel):
    thesis: str
    key_points: List[KeyPoint]
    actionable_takeaways: List[str] = []
    conclusion: str
    tags: List[str]


class EntryResponse(BaseModel):
    id: int
    title: str
    url: str
    content_type: str
    source_name: str
    published_at: Optional[str]
    created_at: Optional[str] = None
    status: str
    summary: Optional[SummaryResponse] = None
    bookmarked: bool = False


class DigestResponse(BaseModel):
    date: str
    entries: List[EntryResponse]


# --- API endpoints ---

@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/sources", response_model=List[SourceResponse])
async def list_sources():
    session = get_session()
    try:
        sources = session.query(Source).all()
        return [SourceResponse.model_validate(s) for s in sources]
    finally:
        session.close()


@app.post("/api/sources", response_model=SourceResponse)
async def create_source(data: SourceCreate):
    session = get_session()
    try:
        source = Source(
            name=data.name,
            platform=data.platform,
            url=data.url,
            rss_url=data.rss_url,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return SourceResponse.model_validate(source)
    finally:
        session.close()


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: int):
    session = get_session()
    try:
        source = session.query(Source).get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        session.delete(source)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.get("/api/digest/{digest_date}", response_model=DigestResponse)
async def get_digest(digest_date: str):
    session = get_session()
    try:
        target_date = datetime.strptime(digest_date, "%Y-%m-%d").date()
        digest = (
            session.query(DailyDigest)
            .filter(DailyDigest.digest_date == target_date)
            .first()
        )

        entries_data = []
        if digest:
            entry_ids = digest.get_entry_ids()
            for eid in entry_ids:
                entry = session.query(Entry).get(eid)
                if entry:
                    entries_data.append(_entry_to_response(session, entry))

        return DigestResponse(date=digest_date, entries=entries_data)
    finally:
        session.close()


@app.get("/api/digest/latest", response_model=DigestResponse)
async def get_latest_digest():
    session = get_session()
    try:
        digest = (
            session.query(DailyDigest)
            .order_by(DailyDigest.digest_date.desc())
            .first()
        )
        if not digest:
            return DigestResponse(date=str(date.today()), entries=[])

        entries_data = []
        for eid in digest.get_entry_ids():
            entry = session.query(Entry).get(eid)
            if entry:
                entries_data.append(_entry_to_response(session, entry))

        return DigestResponse(date=str(digest.digest_date), entries=entries_data)
    finally:
        session.close()


@app.get("/api/entries/{entry_id}", response_model=EntryResponse)
async def get_entry(entry_id: int):
    session = get_session()
    try:
        entry = session.query(Entry).get(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        return _entry_to_response(session, entry)
    finally:
        session.close()


@app.get("/api/entries", response_model=List[EntryResponse])
async def list_entries(limit: int = 20, offset: int = 0, status: Optional[str] = None):
    session = get_session()
    try:
        query = session.query(Entry).order_by(Entry.published_at.desc())
        if status:
            query = query.filter(Entry.status == status)
        entries = query.offset(offset).limit(limit).all()
        return [_entry_to_response(session, e) for e in entries]
    finally:
        session.close()


@app.post("/api/bookmarks/{entry_id}")
async def add_bookmark(entry_id: int):
    session = get_session()
    try:
        entry = session.query(Entry).get(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")

        existing = session.query(Bookmark).filter(Bookmark.entry_id == entry_id).first()
        if existing:
            return {"ok": True, "message": "Already bookmarked"}

        bookmark = Bookmark(entry_id=entry_id)
        session.add(bookmark)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.delete("/api/bookmarks/{entry_id}")
async def remove_bookmark(entry_id: int):
    session = get_session()
    try:
        bookmark = session.query(Bookmark).filter(Bookmark.entry_id == entry_id).first()
        if bookmark:
            session.delete(bookmark)
            session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.get("/api/bookmarks", response_model=List[EntryResponse])
async def list_bookmarks():
    session = get_session()
    try:
        bookmarks = session.query(Bookmark).order_by(Bookmark.created_at.desc()).all()
        entries = []
        for bm in bookmarks:
            entry = session.query(Entry).get(bm.entry_id)
            if entry:
                entries.append(_entry_to_response(session, entry))
        return entries
    finally:
        session.close()


# --- Helpers ---

def _entry_to_response(session, entry: Entry) -> EntryResponse:
    source = session.query(Source).get(entry.source_id)
    summary_data = None
    if entry.summary:
        summary_data = SummaryResponse(
            thesis=entry.summary.thesis,
            key_points=[KeyPoint(**p) for p in entry.summary.get_key_points()],
            actionable_takeaways=entry.summary.get_actionable_takeaways(),
            conclusion=entry.summary.conclusion,
            tags=entry.summary.get_tags(),
        )

    bookmarked = session.query(Bookmark).filter(Bookmark.entry_id == entry.id).first() is not None

    return EntryResponse(
        id=entry.id,
        title=entry.title,
        url=entry.url,
        content_type=entry.content_type,
        source_name=source.name if source else "Unknown",
        published_at=entry.published_at.isoformat() if entry.published_at else None,
        created_at=entry.created_at.isoformat() if entry.created_at else None,
        status=entry.status,
        summary=summary_data,
        bookmarked=bookmarked,
    )


# --- Static files & SPA fallback ---

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        file_path = STATIC_DIR / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(STATIC_DIR / "index.html"))
