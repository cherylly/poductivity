"""Scheduler: runs the pipeline on a cron schedule."""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings

logger = logging.getLogger(__name__)


def start_scheduler():
    """Start the APScheduler with configured cron triggers."""
    import asyncio
    from src.pipeline import run_daily_pipeline

    def run_pipeline_sync():
        asyncio.run(run_daily_pipeline())

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_pipeline_sync,
        CronTrigger(hour=settings.digest_cron_hour, minute=settings.digest_cron_minute),
        id="daily_digest",
        name="Daily content digest pipeline",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler started. Pipeline runs daily at "
        f"{settings.digest_cron_hour:02d}:{settings.digest_cron_minute:02d}"
    )
    print(
        f"✓ Scheduler running. Next digest at "
        f"{settings.digest_cron_hour:02d}:{settings.digest_cron_minute:02d}"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
