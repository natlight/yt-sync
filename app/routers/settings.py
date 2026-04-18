import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from app.config import settings
from app.templating import templates

router = APIRouter(prefix="/settings")


def _disk_usage(path: Path) -> dict | None:
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": usage.total / 1024**3,
            "used_gb": usage.used / 1024**3,
            "free_gb": usage.free / 1024**3,
        }
    except FileNotFoundError:
        return None


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    cookies_mtime = None
    cookies_age_days = None
    if settings.cookies_file.exists():
        ts = settings.cookies_file.stat().st_mtime
        cookies_mtime = datetime.fromtimestamp(ts, tz=timezone.utc)
        cookies_age_days = (datetime.now(timezone.utc) - cookies_mtime).days
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "settings": settings,
            "cookies_exists": settings.cookies_file.exists(),
            "cookies_mtime": cookies_mtime,
            "cookies_age_days": cookies_age_days,
            "archive_usage": _disk_usage(settings.archive_dir),
            "media_usage": _disk_usage(settings.media_root),
            "music_usage": _disk_usage(settings.music_root),
        },
    )


@router.post("/import-yaml", response_class=HTMLResponse)
def import_yaml(request: Request):
    """Import sources from a YAML file (used during migration from CronJob)."""
    from scripts.seed_from_yaml import seed_from_yaml

    yaml_path = Path("/config/sources.yaml")
    if not yaml_path.exists():
        # Fallback for local dev
        yaml_path = Path("/data/sources.yaml")
    if not yaml_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No sources.yaml found at /config/sources.yaml or /data/sources.yaml",
        )
    counts = seed_from_yaml(yaml_path)
    return Response(
        status_code=200,
        headers={"HX-Redirect": "/sources"},
        content=f"Imported: {counts}",
    )
