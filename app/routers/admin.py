"""Admin page: raw scheduler state, job history, and system diagnostics."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, desc, select, text

from app.config import settings
from app.db import engine, get_session
from app.models import JobRun, Source
from app.scheduler import scheduler
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger(__name__)


def _db_path() -> str | None:
    url = settings.db_url
    prefix = "sqlite:///"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None


def _raw_apscheduler_jobs() -> list[dict[str, Any]]:
    """Read the apscheduler_jobs table directly via sqlite3."""
    path = _db_path()
    if not path:
        return []
    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, name, next_run_time, job_state FROM apscheduler_jobs ORDER BY next_run_time"
        ).fetchall()
        con.close()
        result = []
        for r in rows:
            nrt = r["next_run_time"]
            if nrt is not None:
                try:
                    nrt = datetime.fromtimestamp(float(nrt), tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                except Exception:
                    nrt = str(nrt)
            result.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "next_run_time": nrt,
                    "job_state_len": len(r["job_state"]) if r["job_state"] else 0,
                }
            )
        return result
    except Exception as exc:
        log.warning("Could not read apscheduler_jobs: %s", exc)
        return []


def _scheduler_jobs_live() -> list[dict[str, Any]]:
    """Jobs currently loaded in the in-memory APScheduler instance."""
    out = []
    for job in scheduler.get_jobs():
        nrt = job.next_run_time
        out.append(
            {
                "id": job.id,
                "name": job.name or job.id,
                "trigger": str(job.trigger),
                "next_run_time": nrt.strftime("%Y-%m-%d %H:%M:%S %Z") if nrt else "paused",
                "func": f"{job.func.__module__}.{job.func.__qualname__}" if job.func else "?",
                "args": str(job.args),
                "max_instances": job.max_instances,
                "coalesce": job.coalesce,
                "misfire_grace_time": job.misfire_grace_time,
            }
        )
    out.sort(key=lambda j: j["next_run_time"])
    return out


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_page(request: Request, session: Session = Depends(get_session)):
    # Live scheduler state
    live_jobs = _scheduler_jobs_live()

    # Raw DB rows from apscheduler_jobs table
    raw_jobs = _raw_apscheduler_jobs()

    # All sources with their cron/enabled state
    sources = session.exec(select(Source).order_by(Source.name)).all()

    # Discrepancies: sources that are enabled+cron but missing from live scheduler
    live_ids = {j["id"] for j in live_jobs}
    missing_jobs = [
        s for s in sources
        if s.enabled and s.cron and f"source-{s.id}" not in live_ids
    ]

    # Recent job runs (last 200)
    recent_runs = session.exec(
        select(JobRun).order_by(desc(JobRun.created_at)).limit(200)
    ).all()

    # Source name lookup
    source_map = {s.id: s.name for s in sources}

    # DB table row counts
    table_counts: dict[str, int] = {}
    for tbl in ("source", "jobrun", "download", "apscheduler_jobs"):
        try:
            row = session.exec(text(f"SELECT COUNT(*) FROM {tbl}")).one()  # type: ignore[call-overload]
            table_counts[tbl] = row[0]
        except Exception:
            table_counts[tbl] = -1

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "active_page": "admin",
            "scheduler_running": scheduler.running,
            "live_jobs": live_jobs,
            "raw_jobs": raw_jobs,
            "sources": sources,
            "missing_jobs": missing_jobs,
            "recent_runs": recent_runs,
            "source_map": source_map,
            "table_counts": table_counts,
            "db_url": settings.db_url,
            "timezone": settings.timezone,
        },
    )


@router.post("/resync", response_class=HTMLResponse)
def resync_scheduler(request: Request, session: Session = Depends(get_session)):
    """Force a re-sync of scheduler jobs from the database."""
    from app.scheduler import sync_jobs_from_db
    sync_jobs_from_db()
    live_jobs = _scheduler_jobs_live()
    sources = session.exec(select(Source).order_by(Source.name)).all()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "active_page": "admin",
            "scheduler_running": scheduler.running,
            "live_jobs": live_jobs,
            "raw_jobs": _raw_apscheduler_jobs(),
            "sources": sources,
            "missing_jobs": [],
            "recent_runs": session.exec(
                select(JobRun).order_by(desc(JobRun.created_at)).limit(200)
            ).all(),
            "source_map": {s.id: s.name for s in sources},
            "table_counts": {},
            "db_url": settings.db_url,
            "timezone": settings.timezone,
            "resync_done": True,
        },
    )
