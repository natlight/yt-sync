from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, desc, select

from app.db import get_session
from app.models import Download, JobRun, JobStatus, Source
from app.scheduler import scheduler
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    running = session.exec(
        select(JobRun)
        .where(JobRun.status.in_([JobStatus.queued.value, JobStatus.running.value]))  # type: ignore[union-attr]
        .order_by(desc(JobRun.created_at))
    ).all()
    recent_downloads = session.exec(
        select(Download).order_by(desc(Download.started_at)).limit(100)
    ).all()
    upcoming = []
    for job in scheduler.get_jobs():
        if job.next_run_time is None:
            continue
        upcoming.append((job.next_run_time, job.name or job.id))
    upcoming.sort(key=lambda t: t[0])
    upcoming = upcoming[:5]
    source_count = session.exec(select(Source)).all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "running": running,
            "recent_downloads": recent_downloads,
            "upcoming": upcoming,
            "source_count": len(source_count),
            "active_page": "dashboard",
        },
    )


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz(session: Session = Depends(get_session)):
    session.exec(select(Source).limit(1)).all()
    return {"status": "ready", "scheduler_running": scheduler.running}
