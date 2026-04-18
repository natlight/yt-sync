from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlmodel import Session, desc, select

from app import job_service
from app.db import get_session
from app.models import JobRun, JobStatus
from app.templating import templates

router = APIRouter(prefix="/jobs")

TERMINAL = {JobStatus.ok.value, JobStatus.error.value, JobStatus.cancelled.value}


@router.get("/active", response_class=HTMLResponse)
def active(request: Request, session: Session = Depends(get_session)):
    rows = session.exec(
        select(JobRun)
        .where(JobRun.status.in_([JobStatus.queued.value, JobStatus.running.value]))  # type: ignore[union-attr]
        .order_by(desc(JobRun.created_at))
        .limit(20)
    ).all()
    return templates.TemplateResponse(
        request, "partials/active_jobs.html", {"rows": rows}
    )


@router.get("/{job_id}/status", response_class=HTMLResponse)
def get_status(job_id: int, request: Request, session: Session = Depends(get_session)):
    job = session.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    polling = job.status not in TERMINAL
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "job": job, "polling": polling},
    )


@router.post("/{job_id}/cancel", response_class=HTMLResponse)
def cancel(job_id: int, request: Request, session: Session = Depends(get_session)):
    job_service.cancel_job(job_id)
    job = session.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "job": job, "polling": False},
    )


@router.get("/{job_id}/log", response_class=PlainTextResponse)
def log(job_id: int, session: Session = Depends(get_session)):
    job = session.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return job.log_tail or "(no log captured yet)"
