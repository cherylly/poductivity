#!/usr/bin/env python3
"""Batch pre-translate all untranslated summaries."""
import asyncio, sys, os, logging

sys.stdout.reconfigure(line_buffering=True)

for k in ("https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    stream=sys.stdout)

async def main():
    from src.models import get_session, init_db
    from src.pipeline import translate_new_summaries
    init_db()
    session = get_session()
    try:
        count = await translate_new_summaries(session)
        print(f"Total translated: {count}")
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(main())
