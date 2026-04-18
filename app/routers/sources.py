from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, desc, select

from app import scheduler as scheduler_mod
from app.db import get_session
from app.models import Source, SourceType
from app.templating import templates

router = APIRouter(prefix="/sources")


@router.get("", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    sources = session.exec(select(Source).order_by(Source.type, Source.name)).all()
    return templates.TemplateResponse(
        request,
        "sources/index.html",
        {"sources": sources, "active_page": "sources"},
    )


@router.get("/new", response_class=HTMLResponse)
def new(request: Request):
    return templates.TemplateResponse(
        request,
        "sources/form.html",
        {"source": None, "form_action": "/sources", "form_method": "post"},
    )


@router.post("", response_class=HTMLResponse)
def create(
    request: Request,
    type: str = Form(...),
    name: str = Form(...),
    url: str = Form(...),
    cron: str = Form(""),
    enabled: str = Form(""),
    max_downloads: int = Form(25),
    date_after: str = Form(""),
    session: Session = Depends(get_session),
):
    src = Source(
        type=SourceType(type),
        name=name.strip(),
        url=url.strip(),
        cron=cron.strip() or None,
        enabled=enabled == "on",
        max_downloads=max_downloads,
        date_after=date_after.strip() or None,
    )
    session.add(src)
    session.commit()
    session.refresh(src)
    scheduler_mod.upsert_source_job(src)
    # HX-Redirect tells HTMX to do a full-page navigation back to the list.
    return Response(status_code=204, headers={"HX-Redirect": "/sources"})


@router.get("/{source_id}/edit", response_class=HTMLResponse)
def edit(source_id: int, request: Request, session: Session = Depends(get_session)):
    src = session.get(Source, source_id)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        request,
        "sources/form.html",
        {
            "source": src,
            "form_action": f"/sources/{source_id}",
            "form_method": "put",
        },
    )


@router.put("/{source_id}", response_class=HTMLResponse)
def update(
    source_id: int,
    request: Request,
    type: str = Form(...),
    name: str = Form(...),
    url: str = Form(...),
    cron: str = Form(""),
    enabled: str = Form(""),
    max_downloads: int = Form(25),
    date_after: str = Form(""),
    session: Session = Depends(get_session),
):
    src = session.get(Source, source_id)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    src.type = SourceType(type)
    src.name = name.strip()
    src.url = url.strip()
    src.cron = cron.strip() or None
    src.enabled = enabled == "on"
    src.max_downloads = max_downloads
    src.date_after = date_after.strip() or None
    session.add(src)
    session.commit()
    session.refresh(src)
    scheduler_mod.upsert_source_job(src)
    return Response(status_code=204, headers={"HX-Redirect": "/sources"})


@router.delete("/{source_id}")
def delete(source_id: int, session: Session = Depends(get_session)):
    src = session.get(Source, source_id)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    session.delete(src)
    session.commit()
    scheduler_mod.remove_source_job(source_id)
    return Response(status_code=200)


@router.post("/{source_id}/toggle", response_class=HTMLResponse)
def toggle(source_id: int, request: Request, session: Session = Depends(get_session)):
    src = session.get(Source, source_id)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    src.enabled = not src.enabled
    session.add(src)
    session.commit()
    session.refresh(src)
    scheduler_mod.upsert_source_job(src)
    return templates.TemplateResponse(
        request, "sources/_row.html", {"s": src}
    )


@router.post("/{source_id}/run", response_class=HTMLResponse)
async def run_now(source_id: int, request: Request, session: Session = Depends(get_session)):
    from app.job_service import queue_source_run, JobKind

    src = session.get(Source, source_id)
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    job_id = queue_source_run(source_id, kind=JobKind.manual)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "job": None, "polling": True},
    )
