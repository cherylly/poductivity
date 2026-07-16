from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import feedparser
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.models import Bookmark, DailyDigest, Entry, Source, Summary, get_session, init_db

logger = logging.getLogger(__name__)

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
    transcript_source: Optional[str] = None


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
async def list_entries(limit: int = 20, offset: int = 0, status: Optional[str] = None, lite: bool = False, source_id: Optional[int] = None):
    session = get_session()
    try:
        query = session.query(Entry).order_by(Entry.published_at.desc())
        if status:
            query = query.filter(Entry.status == status)
        if source_id:
            query = query.filter(Entry.source_id == source_id)
        entries = query.offset(offset).limit(limit).all()
        return [_entry_to_response(session, e, lite=lite) for e in entries]
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


# --- News API (智驾行业新闻) ---

GOOGLE_NEWS_QUERIES = [
    "自动驾驶 OR 智驾 OR Robotaxi OR 无人驾驶",
    "autonomous driving OR self-driving OR robotaxi",
]

_news_cache: List[dict] = []
_news_cache_time: Optional[datetime] = None


def _fetch_news_from_google() -> List[dict]:
    """Fetch autonomous driving news from Google News RSS search."""
    import urllib.parse
    from time import mktime
    from bs4 import BeautifulSoup

    all_news = []
    seen_titles = set()

    for query in GOOGLE_NEWS_QUERIES:
        encoded = urllib.parse.quote(query)
        is_cn = any(c > "\u4e00" for c in query)
        if is_cn:
            url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        else:
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:40]:
                title = getattr(entry, "title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                src_obj = getattr(entry, "source", None)
                source_name = ""
                if src_obj:
                    source_name = getattr(src_obj, "title", "") or src_obj.get("title", "")

                # Clean " - SourceName" suffix from title if source is known
                if source_name and title.endswith(f" - {source_name}"):
                    title = title[: -(len(source_name) + 3)].strip()

                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime.fromtimestamp(mktime(entry.published_parsed)).strftime("%Y-%m-%d %H:%M")

                summary_raw = getattr(entry, "summary", "") or ""
                clean_summary = BeautifulSoup(summary_raw, "html.parser").get_text()[:300]

                link = getattr(entry, "link", "")

                all_news.append({
                    "title": title,
                    "source": source_name,
                    "published_at": published,
                    "url": link,
                    "summary": clean_summary,
                    "tags": [],
                })
        except Exception as e:
            logger.warning(f"Failed to fetch Google News for query '{query}': {e}")

    all_news.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_news[:10]


class NewsItem(BaseModel):
    title: str
    source: str
    published_at: str
    url: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = []


@app.get("/api/news", response_model=List[NewsItem])
async def get_news():
    """获取智驾行业新闻（带1小时缓存）"""
    global _news_cache, _news_cache_time
    now = datetime.now()
    if _news_cache and _news_cache_time and (now - _news_cache_time).seconds < 86400:
        return _news_cache
    _news_cache = _fetch_news_from_google()
    _news_cache_time = now
    return _news_cache


@app.post("/api/news/fetch", response_model=List[NewsItem])
async def fetch_news():
    """强制刷新新闻"""
    global _news_cache, _news_cache_time
    _news_cache = _fetch_news_from_google()
    _news_cache_time = datetime.now()
    return _news_cache


# --- Thinking API (每日思考 - LLM生成面试问题) ---

_thinking_cache: List[dict] = []
_thinking_cache_date: Optional[date] = None

THINKING_PROMPT = """你是一位资深的出海销售面试教练。请生成3个高质量的出海/海外销售行业面试问题。

要求：
1. 每个问题都要有实际深度，不要泛泛而谈
2. 覆盖不同维度：如市场开拓、客户管理、谈判技巧、跨文化沟通、渠道管理、竞品分析、数据驱动、团队管理等
3. 今天的日期是 {today}，可以结合近期行业热点（如新能源出海、东南亚/中东/拉美市场、AI赋能销售等）
4. 问题要有挑战性，适合中高级候选人

返回 JSON 数组，每个元素格式：
[
  {{
    "question": "面试问题",
    "context": "问题背景说明（为什么会问这个问题，考察什么能力）",
    "answer": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "tips": "答题技巧提示"
  }}
]

只返回 JSON，不要其他内容。"""


async def _generate_thinking_questions() -> List[dict]:
    """Use LLM to generate daily interview questions."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.anthropic_auth_token,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": THINKING_PROMPT.format(today=date.today().isoformat())}],
            temperature=0.8,
            max_tokens=2000,
            timeout=30,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to generate thinking questions: {e}")
        return []


class QuestionItem(BaseModel):
    question: str
    context: Optional[str] = None
    answer: Optional[List[str]] = None
    tips: Optional[str] = None


@app.get("/api/thinking/questions", response_model=List[QuestionItem])
async def get_questions():
    """获取今日面试问题（每天缓存）"""
    global _thinking_cache, _thinking_cache_date
    today = date.today()
    if _thinking_cache and _thinking_cache_date == today:
        return _thinking_cache
    _thinking_cache = await _generate_thinking_questions()
    _thinking_cache_date = today
    return _thinking_cache


@app.post("/api/thinking/generate", response_model=List[QuestionItem])
async def generate_questions():
    """强制生成新问题"""
    global _thinking_cache, _thinking_cache_date
    _thinking_cache = await _generate_thinking_questions()
    _thinking_cache_date = date.today()
    return _thinking_cache


class DailyQuestionsResponse(BaseModel):
    date: str
    questions: List[QuestionItem]


@app.get("/api/thinking/history", response_model=List[DailyQuestionsResponse])
async def get_question_history(limit: int = 30):
    """历史记录（LLM模式下不持久化，返回空列表）"""
    return []


@app.get("/api/thinking/history/{date_str}", response_model=DailyQuestionsResponse)
async def get_questions_by_date(date_str: str):
    """获取指定日期的问题（LLM模式下不持久化）"""
    raise HTTPException(status_code=404, detail="No questions found for this date")


# --- Translation API (Google Translate, fast) ---

_translation_cache: dict = {}


def _google_translate(text: str, target: str = "zh-CN") -> str:
    """Translate text using free Google Translate API."""
    if not text or not text.strip():
        return text
    import urllib.request
    import urllib.parse
    encoded = urllib.parse.quote(text[:4500])
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target}&dt=t&q={encoded}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception as e:
        logger.warning(f"Google translate failed: {e}")
        return text


@app.post("/api/entries/{entry_id}/translate")
async def translate_entry(entry_id: int):
    if entry_id in _translation_cache:
        return _translation_cache[entry_id]

    session = get_session()
    try:
        entry = session.query(Entry).get(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        if not entry.summary:
            raise HTTPException(status_code=400, detail="No summary to translate")

        summary = entry.summary
        key_points_orig = summary.get_key_points()
        takeaways_orig = summary.get_actionable_takeaways()
        tags_orig = summary.get_tags()

        import asyncio
        loop = asyncio.get_event_loop()

        title_t = await loop.run_in_executor(None, _google_translate, entry.title)
        thesis_t = await loop.run_in_executor(None, _google_translate, summary.thesis or "")
        conclusion_t = await loop.run_in_executor(None, _google_translate, summary.conclusion or "")

        kp_translated = []
        for p in key_points_orig:
            topic_t = await loop.run_in_executor(None, _google_translate, p.get("topic", "")) if p.get("topic") else ""
            text_t = await loop.run_in_executor(None, _google_translate, p.get("text", ""))
            kp_translated.append({
                "topic": topic_t,
                "text": text_t,
                "timestamp": p.get("timestamp", ""),
            })

        takeaways_t = []
        for t in takeaways_orig:
            takeaways_t.append(await loop.run_in_executor(None, _google_translate, t))

        tags_t = []
        for tag in tags_orig:
            tags_t.append(await loop.run_in_executor(None, _google_translate, tag))

        translated = {
            "title": title_t,
            "thesis": thesis_t,
            "key_points": kp_translated,
            "actionable_takeaways": takeaways_t,
            "conclusion": conclusion_t,
            "tags": tags_t,
        }
        _translation_cache[entry_id] = translated
        return translated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translation failed for entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    finally:
        session.close()


# --- Helpers ---

def _entry_to_response(session, entry: Entry, lite: bool = False) -> EntryResponse:
    source = session.query(Source).get(entry.source_id)
    summary_data = None
    if entry.summary:
        if lite:
            thesis = entry.summary.thesis or ""
            summary_data = SummaryResponse(
                thesis=thesis[:200] + "..." if len(thesis) > 200 else thesis,
                key_points=[],
                actionable_takeaways=[],
                conclusion="",
                tags=entry.summary.get_tags()[:4],
            )
        else:
            summary_data = SummaryResponse(
                thesis=entry.summary.thesis,
                key_points=[KeyPoint(**p) for p in entry.summary.get_key_points()],
                actionable_takeaways=entry.summary.get_actionable_takeaways(),
                conclusion=entry.summary.conclusion,
                tags=entry.summary.get_tags(),
            )

    bookmarked = session.query(Bookmark).filter(Bookmark.entry_id == entry.id).first() is not None

    transcript_source = None
    if entry.content_type == "video" and entry.raw_text:
        if entry.raw_text.startswith("[Video description]"):
            transcript_source = "description"
        elif entry.raw_text.startswith("["):
            transcript_source = "transcript"

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
        transcript_source=transcript_source,
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
