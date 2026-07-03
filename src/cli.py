"""CLI interface for Content Digest."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from src.config import settings
from src.models import Entry, Source, Summary, get_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_init(args):
    """Initialize database."""
    init_db()
    print("✓ Database initialized")


def cmd_add_source(args):
    """Add a new subscription source."""
    init_db()
    session = get_session()

    source = Source(
        name=args.name,
        platform=args.platform,
        url=args.url,
        rss_url=args.rss_url,
    )
    session.add(source)
    session.commit()
    print(f"✓ Added source: {args.name} ({args.platform})")
    session.close()


def cmd_list_sources(args):
    """List all subscription sources."""
    init_db()
    session = get_session()
    sources = session.query(Source).all()

    if not sources:
        print("No sources configured. Use 'digest add' to add one.")
        return

    print(f"\n{'ID':<4} {'Platform':<10} {'Name':<30} {'Active':<8} {'URL'}")
    print("-" * 100)
    for s in sources:
        status = "✓" if s.active else "✗"
        print(f"{s.id:<4} {s.platform:<10} {s.name:<30} {status:<8} {s.url}")
    print()
    session.close()


def cmd_remove_source(args):
    """Remove a subscription source."""
    init_db()
    session = get_session()
    source = session.query(Source).get(args.id)
    if not source:
        print(f"✗ Source ID {args.id} not found")
        return
    session.delete(source)
    session.commit()
    print(f"✓ Removed source: {source.name}")
    session.close()


def cmd_run(args):
    """Run the digest pipeline manually."""
    from src.pipeline import run_daily_pipeline
    asyncio.run(run_daily_pipeline())


def cmd_status(args):
    """Show recent pipeline status."""
    init_db()
    session = get_session()

    total_sources = session.query(Source).filter(Source.active == True).count()
    total_entries = session.query(Entry).count()
    done_entries = session.query(Entry).filter(Entry.status == "done").count()
    failed_entries = session.query(Entry).filter(Entry.status == "failed").count()
    pending_entries = session.query(Entry).filter(Entry.status == "pending").count()

    print(f"\n📊 Content Digest Status")
    print(f"{'='*40}")
    print(f"  Active sources:  {total_sources}")
    print(f"  Total entries:   {total_entries}")
    print(f"  ✓ Completed:     {done_entries}")
    print(f"  ⏳ Pending:       {pending_entries}")
    print(f"  ✗ Failed:        {failed_entries}")
    print()

    # Recent entries
    recent = session.query(Entry).order_by(Entry.created_at.desc()).limit(5).all()
    if recent:
        print("Recent entries:")
        for e in recent:
            status_icon = {"done": "✓", "failed": "✗", "pending": "⏳"}.get(e.status, "?")
            print(f"  {status_icon} [{e.content_type}] {e.title[:50]}")
    print()
    session.close()


def cmd_search_podcast(args):
    """Search for a podcast RSS by name."""
    from src.fetchers.podcast import PodcastFetcher

    results = asyncio.run(PodcastFetcher.search_podcast_rss(args.query))
    if not results:
        print("No podcasts found. Make sure PODCAST_INDEX_KEY and PODCAST_INDEX_SECRET are set.")
        return

    print(f"\nSearch results for: '{args.query}'")
    print("-" * 60)
    for i, r in enumerate(results, 1):
        print(f"\n  {i}. {r['name']}")
        print(f"     RSS: {r['rss_url']}")
        if r['description']:
            print(f"     {r['description'][:80]}...")
    print()


def cmd_serve(args):
    """Start the web server."""
    import uvicorn
    from src.web import app
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


def main():
    parser = argparse.ArgumentParser(
        prog="digest",
        description="Content Digest - Personal content aggregation & AI summarization",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init
    subparsers.add_parser("init", help="Initialize database")

    # add
    add_parser = subparsers.add_parser("add", help="Add a subscription source")
    add_parser.add_argument("--name", required=True, help="Source name")
    add_parser.add_argument("--platform", required=True, choices=["substack", "youtube", "podcast"])
    add_parser.add_argument("--url", required=True, help="Source URL")
    add_parser.add_argument("--rss-url", help="Override RSS URL (optional)")

    # list
    subparsers.add_parser("list", help="List subscription sources")

    # remove
    rm_parser = subparsers.add_parser("remove", help="Remove a source by ID")
    rm_parser.add_argument("id", type=int)

    # run
    subparsers.add_parser("run", help="Run digest pipeline now")

    # status
    subparsers.add_parser("status", help="Show pipeline status")

    # search-podcast
    sp_parser = subparsers.add_parser("search-podcast", help="Search podcast by name")
    sp_parser.add_argument("query", help="Podcast name to search")

    # serve
    subparsers.add_parser("serve", help="Start web server")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "add": cmd_add_source,
        "list": cmd_list_sources,
        "remove": cmd_remove_source,
        "run": cmd_run,
        "status": cmd_status,
        "search-podcast": cmd_search_podcast,
        "serve": cmd_serve,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
