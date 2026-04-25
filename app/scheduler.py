"""APScheduler singleton wired to the same SQLite DB as the app."""
from __future__ import annotations

import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.job_service import run_source_now
from app.models import Source

log = logging.getLogger(__name__)


def _job_id(source_id: int) -> str:
    return f"source-{source_id}"


def _build_scheduler() -> AsyncIOScheduler:
    jobstore = SQLAlchemyJobStore(
        url=settings.db_url, tablename="apscheduler_jobs"
    )
    return AsyncIOScheduler(jobstores={"default": jobstore})


scheduler: AsyncIOScheduler = _build_scheduler()


def upsert_source_job(source: Source) -> None:
    """Add/replace the APScheduler job for a Source. Removes if not eligible."""
    if source.id is None:
        return
    job_id = _job_id(source.id)
    if not source.enabled or not source.cron:
        try:
            scheduler.remove_job(job_id)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        trigger = CronTrigger.from_crontab(source.cron, timezone=settings.timezone)
    except ValueError:
        log.warning("Source %s has invalid cron %r — skipping", source.id, source.cron)
        try:
            scheduler.remove_job(job_id)
        except Exception:  # noqa: BLE001
            pass
        return
    scheduler.add_job(
        run_source_now,
        trigger=trigger,
        args=[source.id],
        id=job_id,
        name=f"{source.type}: {source.name}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )


def remove_source_job(source_id: int) -> None:
    try:
        scheduler.remove_job(_job_id(source_id))
    except Exception:  # noqa: BLE001
        pass


def sync_jobs_from_db() -> None:
    """On startup: ensure scheduled jobs match enabled+cron Sources in DB."""
    with Session(engine) as session:
        sources = session.exec(select(Source)).all()
    desired_ids: set[str] = set()
    for s in sources:
        if s.id is not None and s.enabled and s.cron:
            desired_ids.add(_job_id(s.id))
            upsert_source_job(s)
    for job in list(scheduler.get_jobs()):
        if job.id.startswith("source-") and job.id not in desired_ids:
            scheduler.remove_job(job.id)


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    sync_jobs_from_db()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
