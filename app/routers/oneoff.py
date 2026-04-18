from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app import job_service
from app.templating import templates

router = APIRouter(prefix="/oneoff")


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "oneoff/index.html", {"active_page": "oneoff"}
    )


@router.post("", response_class=HTMLResponse)
async def submit(
    request: Request,
    url: str = Form(...),
    type: str = Form("video"),
):
    job_id = job_service.queue_oneoff(url=url.strip(), kind=type)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "job": None, "polling": True},
    )
