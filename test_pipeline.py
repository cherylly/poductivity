#!/usr/bin/env python3
"""Quick test script to verify the full pipeline works end-to-end.

Usage:
    1. Set ANTHROPIC_AUTH_TOKEN in .env file
    2. Run: no_proxy="*" python test_pipeline.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


async def test_llm():
    """Test LLM summarization with a small sample."""
    from src.config import settings
    from src.summarizer.llm import generate_summary

    if not settings.anthropic_auth_token:
        print("✗ ANTHROPIC_AUTH_TOKEN not set in .env")
        print("  Please set it and try again.")
        return False

    print(f"Testing LLM API ({settings.llm_base_url}, model={settings.llm_model})...")

    sample_text = """
    The future of AI is not about replacing humans, but augmenting them.
    According to recent research, AI tools that work alongside humans produce
    30% better outcomes than either alone. The key insight is that AI excels
    at pattern recognition and data processing, while humans bring creativity,
    empathy, and judgment. Companies that embrace this collaborative approach
    are seeing 2x productivity gains in their engineering teams.
    """

    result = await generate_summary(
        text=sample_text,
        title="AI Augmentation: The Path Forward",
        content_type="article",
        source_name="Test Source",
    )

    if result:
        print("✓ LLM Summary generated successfully!")
        print(f"  Thesis: {result['thesis']}")
        print(f"  Key points: {len(result['key_points'])}")
        print(f"  Tags: {result.get('tags', [])}")
        return True
    else:
        print("✗ LLM returned None - check logs")
        return False


async def test_full_pipeline():
    """Test fetch + summarize for one entry."""
    from src.models import Entry, Source, get_session, init_db
    from src.pipeline import summarize_entries

    init_db()
    session = get_session()

    entry = session.query(Entry).filter(Entry.status == "summarizing").first()
    if not entry:
        print("✗ No entries in 'summarizing' status to test")
        print("  Run 'python -m src.cli run' first to fetch content")
        return False

    print(f"Testing summarization of: '{entry.title[:60]}...'")
    count = await summarize_entries(session, [entry])
    session.close()

    if count > 0:
        print(f"✓ Full pipeline works! Summarized {count} entry")
        return True
    else:
        print("✗ Summarization failed - check error_message in DB")
        return False


async def main():
    print("=" * 50)
    print("Content Digest - End-to-End Test")
    print("=" * 50)

    # Test 1: LLM connectivity
    print("\n[1/2] Testing LLM API...")
    llm_ok = await test_llm()

    if not llm_ok:
        print("\n⚠ LLM test failed. Fix the token and try again.")
        return

    # Test 2: Full pipeline
    print("\n[2/2] Testing full pipeline...")
    await test_full_pipeline()

    print("\n" + "=" * 50)
    print("Done! If both tests passed, run 'python -m src.cli run' to process all entries.")


if __name__ == "__main__":
    asyncio.run(main())
