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
    return all_news[:30]


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
    if _news_cache and _news_cache_time and (now - _news_cache_time).seconds < 3600:
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


# --- Thinking API (每日思考 - 面试问题) ---

INTERVIEW_QUESTIONS = [
    {
        "question": "如何评估一个海外市场的进入时机是否成熟？",
        "context": "在海外销售中，市场时机往往决定了成败。需要从市场成熟度、竞争格局、法规政策等多维度分析。",
        "answer": [
            "分析目标市场的经济增长趋势和消费者购买力变化",
            "评估本地竞争者的市场占有率和产品竞争力",
            "研究当地的法规政策是否对外资企业友好",
            "考察供应链和物流基础设施的完善程度",
            "判断企业文化差异带来的进入门槛"
        ],
        "tips": "建议用数据支撑你的分析，展示你对市场调研方法的理解"
    },
    {
        "question": "如果客户对价格敏感，你会如何进行价值销售？",
        "context": "海外客户往往对价格非常敏感，如何在价格谈判中突出产品价值是关键能力。",
        "answer": [
            "先了解客户的具体痛点和业务目标",
            "用ROI计算展示产品带来的长期收益",
            "强调独特的技术优势和服务保障",
            "提供分阶段付款或试用方案降低风险",
            "分享同行业成功案例增强信心"
        ],
        "tips": "准备2-3个真实的价格谈判案例，展示你的谈判技巧"
    },
    {
        "question": "你如何处理跨文化沟通中的误解？",
        "context": "海外销售需要与不同文化背景的客户打交道，文化敏感度是必备能力。",
        "answer": [
            "主动学习和了解目标市场的文化习俗",
            "保持开放心态，不预设立场",
            "遇到误解时，耐心倾听并确认理解",
            "使用简单清晰的语言，避免俚语和文化隐喻",
            "必要时寻求本地同事或翻译的帮助"
        ],
        "tips": "可以举一个你成功化解跨文化冲突的具体例子"
    },
    {
        "question": "如何制定一个新市场的销售策略？",
        "context": "制定新市场策略需要综合考虑市场分析、渠道选择、团队建设等多个方面。",
        "answer": [
            "进行市场调研，了解市场规模和竞争格局",
            "确定目标客户群体和购买决策流程",
            "选择合适的销售渠道（直销/代理商/线上）",
            "制定本地化的营销推广计划",
            "建立销售团队和培训体系"
        ],
        "tips": "最好准备一个你参与过的新市场开拓案例"
    },
    {
        "question": "你如何看待竞争对手？如何应对价格战？",
        "context": "海外市场竞争激烈，如何正确看待竞争并制定应对策略。",
        "answer": [
            "尊重竞争对手，学习他们的优势",
            "不盲目打价格战，聚焦差异化价值",
            "深入了解客户需求，提供定制化方案",
            "强化服务壁垒，提升客户粘性",
            "必要时寻求总部资源支持"
        ],
        "tips": "用具体案例说明你如何应对过价格竞争"
    },
    {
        "question": "如何建立和维护海外大客户关系？",
        "context": "大客户是海外销售的重要资源，需要系统化的关系管理方法。",
        "answer": [
            "深入了解客户组织架构和决策流程",
            "定期拜访保持沟通，建立信任",
            "提供超出期望的服务支持",
            "邀请客户参观公司或工厂增强信心",
            "建立多层级关系，不依赖单一联系人"
        ],
        "tips": "准备一个你成功维护大客户关系的故事"
    },
    {
        "question": "如果产品在海外市场出现问题，你会如何处理？",
        "context": "海外售后和危机处理能力是考察重点，展示你的问题解决能力。",
        "answer": [
            "第一时间响应客户，展示负责态度",
            "快速定位问题根源，评估影响范围",
            "提供临时解决方案减少客户损失",
            "协调总部资源进行根本性修复",
            "事后总结并优化流程避免复发"
        ],
        "tips": "建议准备一个具体的危机处理案例"
    },
    {
        "question": "你如何利用数据驱动销售决策？",
        "context": "现代销售越来越依赖数据分析能力，展示你的数据思维。",
        "answer": [
            "建立销售漏斗，追踪各阶段转化率",
            "分析客户行为数据优化触达策略",
            "用CRM系统管理客户信息和跟进记录",
            "定期复盘销售数据找出改进机会",
            "预测销售趋势，提前调整资源"
        ],
        "tips": "准备具体的数据分析案例和改进成果"
    },
    {
        "question": "如何与海外代理商/经销商合作？",
        "context": "渠道管理是海外销售的重要技能，需要展示你的渠道合作经验。",
        "answer": [
            "选择有实力且价值观匹配的合作伙伴",
            "明确合作条款和双方权责",
            "提供充分的产品培训和销售支持",
            "建立定期沟通机制，解决问题",
            "设置合理的销售目标和激励政策"
        ],
        "tips": "如有渠道管理经验，一定要用具体案例说明"
    }
]


class QuestionItem(BaseModel):
    question: str
    context: Optional[str] = None
    answer: Optional[List[str]] = None
    tips: Optional[str] = None


@app.get("/api/thinking/questions", response_model=List[QuestionItem])
async def get_questions():
    """获取今日面试问题"""
    # 每天随机选择3个问题
    today = date.today()
    random.seed(today.toordinal())
    return random.sample(INTERVIEW_QUESTIONS, 3)


@app.post("/api/thinking/generate", response_model=List[QuestionItem])
async def generate_questions():
    """生成新的面试问题"""
    # 随机选择3个问题
    return random.sample(INTERVIEW_QUESTIONS, 3)


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
