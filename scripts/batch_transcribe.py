"""Batch transcribe all podcast entries and regenerate summaries."""

import asyncio
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

from src.models import Entry, Source, Summary, get_session, init_db
from src.transcriber.groq_whisper import transcribe_audio
from src.summarizer.llm import generate_summary


async def main():
    init_db()
    session = get_session()

    entries = (
        session.query(Entry)
        .filter(
            Entry.content_type == "podcast",
            Entry.audio_url.isnot(None),
        )
        .all()
    )

    to_process = [
        e for e in entries
        if e.raw_text and e.raw_text.startswith("[Episode description]")
    ]
    print(f"Entries to transcribe: {len(to_process)}")

    success = 0
    failed = 0

    for i, entry in enumerate(to_process):
        print(f"\n[{i + 1}/{len(to_process)}] {entry.title[:60]}")

        try:
            t0 = time.time()
            transcript = await transcribe_audio(entry.audio_url)
            t1 = time.time()

            if not transcript or len(transcript) < 100:
                print(f"  SKIP: transcript too short or failed")
                failed += 1
                continue

            print(f"  Transcribed: {len(transcript)} chars in {t1 - t0:.1f}s")

            entry.raw_text = transcript

            source = session.get(Source, entry.source_id)
            result = await generate_summary(
                text=transcript,
                title=entry.title,
                content_type="podcast",
                source_name=source.name if source else "",
            )

            if result:
                existing = session.query(Summary).filter(Summary.entry_id == entry.id).first()
                summary = existing if existing else Summary(entry_id=entry.id)
                if not existing:
                    session.add(summary)

                summary.thesis = result["thesis"]
                summary.conclusion = result["conclusion"]
                summary.set_key_points(result["key_points"])
                summary.set_actionable_takeaways(result.get("actionable_takeaways", []))
                summary.set_tags(result.get("tags", []))
                entry.status = "done"
                session.commit()

                kp_count = len(result["key_points"])
                ta_count = len(result.get("actionable_takeaways", []))
                print(f"  Summarized: {kp_count} key points, {ta_count} takeaways")
                success += 1
            else:
                print(f"  Summary generation failed")
                failed += 1

            await asyncio.sleep(3)

        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
            session.commit()
            await asyncio.sleep(5)

    session.close()
    print(f"\n=== Done: {success} success, {failed} failed ===")


if __name__ == "__main__":
    asyncio.run(main())
