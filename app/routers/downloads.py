from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, desc, select

from app.db import get_session
from app.models import Download, Source, SourceType
from app.templating import templates

router = APIRouter(prefix="/downloads")


def _query(session: Session, type: str | None, status: str | None, source_id: int | None, q: str | None):
    stmt = select(Download, Source).join(Source, isouter=True).order_by(desc(Download.started_at))
    if type:
        stmt = stmt.where(Source.type == SourceType(type))
    if status:
        stmt = stmt.where(Download.status == status)
    if source_id:
        stmt = stmt.where(Download.source_id == source_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Download.title.ilike(like)) | (Download.video_id.ilike(like)))  # type: ignore[union-attr]
    return session.exec(stmt.limit(200)).all()


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    rows = _query(session, type, status, source_id, q)
    sources = session.exec(select(Source).order_by(Source.name)).all()
    return templates.TemplateResponse(
        request,
        "downloads/index.html",
        {
            "rows": rows,
            "sources": sources,
            "active_page": "downloads",
            "filter_type": type or "",
            "filter_status": status or "",
            "filter_source_id": source_id or "",
            "filter_q": q or "",
        },
    )


@router.get("/table", response_class=HTMLResponse)
def table(
    request: Request,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    rows = _query(session, type, status, source_id, q)
    return templates.TemplateResponse(
        request, "downloads/_table.html", {"rows": rows}
    )
