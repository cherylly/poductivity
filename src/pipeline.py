"""Core pipeline: orchestrates fetch → summarize → store → deliver."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_

from src.config import settings
from src.delivery.email import send_daily_digest
from src.fetchers.podcast import PodcastFetcher
from src.fetchers.substack import SubstackFetcher
from src.fetchers.youtube import YouTubeFetcher
from src.models import DailyDigest, Entry, Source, Summary, get_session, init_db
from src.summarizer.llm import generate_summary
from src.transcriber.groq_whisper import transcribe_audio

logger = logging.getLogger(__name__)

FETCHERS = {
    "substack": SubstackFetcher(),
    "youtube": YouTubeFetcher(),
    "podcast": PodcastFetcher(),
}


async def run_daily_pipeline():
    """Execute the full daily content processing pipeline."""
    logger.info("=== Starting daily pipeline ===")
    init_db()

    session = get_session()
    try:
        # Step 1: Fetch new content from all active sources
        new_entries = await fetch_all_sources(session)
        logger.info(f"Fetched {len(new_entries)} new entries")

        # Step 2: Transcribe podcast entries that have audio but no transcript
        await transcribe_pending_podcasts(session)

        # Step 3: Also pick up any previously pending entries
        pending = (
            session.query(Entry)
            .filter(Entry.status.in_(["pending", "summarizing"]))
            .filter(Entry.raw_text.isnot(None))
            .all()
        )
        entries_to_summarize = list({e.id: e for e in new_entries + pending}.values())

        # Step 4: Generate summaries
        summarized = await summarize_entries(session, entries_to_summarize)
        logger.info(f"Summarized {summarized} entries")

        # Step 5: Create daily digest record
        done_entries = (
            session.query(Entry)
            .filter(Entry.status == "done")
            .filter(Entry.summary.has())
            .order_by(Entry.published_at.desc())
            .limit(50)
            .all()
        )
        digest = create_daily_digest(session, done_entries)

        # Step 6: Send email
        if digest and done_entries:
            send_digest_email(session, digest)

        session.commit()
        logger.info("=== Daily pipeline completed ===")

    except Exception as e:
        session.rollback()
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise
    finally:
        session.close()


async def transcribe_pending_podcasts(session):
    """Transcribe podcast entries that have audio_url but only description-based text."""
    from src.config import settings

    if not settings.groq_api_key:
        logger.info("Groq API key not configured, skipping podcast transcription")
        return

    entries = (
        session.query(Entry)
        .filter(
            Entry.content_type == "podcast",
            Entry.audio_url.isnot(None),
            Entry.status.in_(["pending", "summarizing"]),
        )
        .all()
    )

    needs_transcription = [
        e for e in entries
        if not e.raw_text or e.raw_text.startswith("[Episode description]")
    ]

    if not needs_transcription:
        return

    logger.info(f"Transcribing {len(needs_transcription)} podcast episodes via Groq Whisper")

    for entry in needs_transcription:
        try:
            transcript = await transcribe_audio(entry.audio_url)
            if transcript and len(transcript) > 100:
                entry.raw_text = transcript
                entry.status = "summarizing"
                logger.info(f"Transcribed: {entry.title[:50]} ({len(transcript)} chars)")
            else:
                logger.warning(f"Transcription too short or failed for: {entry.title[:50]}")
        except Exception as e:
            logger.error(f"Transcription error for '{entry.title}': {e}")

    session.commit()


async def fetch_all_sources(session) -> list[Entry]:
    """Fetch new entries from all active sources."""
    sources = session.query(Source).filter(Source.active == True).all()
    all_new_entries = []

    for source in sources:
        try:
            fetcher = FETCHERS.get(source.platform)
            if not fetcher:
                logger.warning(f"No fetcher for platform: {source.platform}")
                continue

            # Find the latest entry we already have for this source
            latest = (
                session.query(Entry)
                .filter(Entry.source_id == source.id)
                .order_by(Entry.published_at.desc())
                .first()
            )
            since = latest.published_at if latest else None

            rss_url = source.rss_url or source.url
            fetched = await fetcher.fetch_new_entries(rss_url, since=since)

            for item in fetched:
                existing = session.query(Entry).filter(
                    Entry.title == item.title,
                    Entry.source_id == source.id,
                ).first()
                if existing:
                    continue

                entry = Entry(
                    source_id=source.id,
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    content_type=item.content_type,
                    raw_text=item.raw_text,
                    audio_url=getattr(item, "audio_url", None),
                    status="pending" if not item.raw_text else "summarizing",
                )
                session.add(entry)
                session.flush()
                all_new_entries.append(entry)

        except Exception as e:
            logger.error(f"Failed to fetch source '{source.name}': {e}")
            continue

    session.commit()
    return all_new_entries


async def summarize_entries(session, entries: list[Entry]) -> int:
    """Generate summaries for entries that have raw text (with concurrency)."""
    MAX_CONCURRENT = 5
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    no_text = []
    to_summarize = []
    for entry in entries:
        if not entry.raw_text:
            no_text.append(entry)
        else:
            to_summarize.append(entry)

    for entry in no_text:
        if entry.content_type == "podcast":
            entry.status = "pending"
        else:
            entry.status = "failed"
            entry.error_message = "No text content available"
    session.commit()

    results = {}

    async def _summarize_one(entry):
        source = session.query(Source).get(entry.source_id)
        async with semaphore:
            return await generate_summary(
                text=entry.raw_text,
                title=entry.title,
                content_type=entry.content_type,
                source_name=source.name if source else "",
            )

    tasks = []
    for entry in to_summarize:
        entry.status = "summarizing"
        tasks.append((entry, asyncio.create_task(_summarize_one(entry))))
    session.commit()

    count = 0
    for entry, task in tasks:
        try:
            result = await task
            if result:
                existing = session.query(Summary).filter(Summary.entry_id == entry.id).first()
                if existing:
                    summary = existing
                else:
                    summary = Summary(entry_id=entry.id)
                    session.add(summary)

                summary.thesis = result["thesis"]
                summary.conclusion = result["conclusion"]
                summary.word_count = len(result["thesis"]) + sum(
                    len(p.get("text", "")) for p in result["key_points"]
                ) + sum(
                    len(t) for t in result.get("actionable_takeaways", [])
                )
                summary.set_key_points(result["key_points"])
                summary.set_actionable_takeaways(result.get("actionable_takeaways", []))
                summary.set_tags(result.get("tags", []))
                entry.status = "done"
                count += 1

                if count % 10 == 0:
                    session.commit()

                logger.info(f"Summarized [{count}/{len(to_summarize)}]: {entry.title[:50]}")
            else:
                entry.status = "failed"
                entry.error_message = "LLM summary generation returned None"
        except Exception as e:
            entry.status = "failed"
            entry.error_message = str(e)
            logger.error(f"Failed to summarize '{entry.title}': {e}")

    session.commit()
    return count


def create_daily_digest(session, entries: list[Entry]) -> DailyDigest | None:
    """Create or update today's digest record."""
    today = date.today()

    digest = session.query(DailyDigest).filter(DailyDigest.digest_date == today).first()
    if not digest:
        digest = DailyDigest(digest_date=today)
        session.add(digest)

    entry_ids = [e.id for e in entries if e.status == "done"]
    digest.set_entry_ids(entry_ids)
    session.commit()
    return digest


def send_digest_email(session, digest: DailyDigest):
    """Send the daily digest email."""
    entry_ids = digest.get_entry_ids()
    if not entry_ids:
        return

    entries_data = []
    for entry_id in entry_ids:
        entry = session.query(Entry).get(entry_id)
        if not entry:
            continue
        source = session.query(Source).get(entry.source_id)
        summary_data = None
        if entry.summary:
            summary_data = {
                "thesis": entry.summary.thesis,
                "key_points": entry.summary.get_key_points(),
                "conclusion": entry.summary.conclusion,
            }
        entries_data.append({
            "id": entry.id,
            "title": entry.title,
            "url": entry.url,
            "content_type": entry.content_type,
            "source_name": source.name if source else "Unknown",
            "summary": summary_data,
        })

    date_str = digest.digest_date.strftime("%b %d, %Y")
    success = send_daily_digest(date_str, entries_data)
    if success:
        digest.email_sent = True
        session.commit()
