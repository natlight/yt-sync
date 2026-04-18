import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import downloads, jobs, oneoff, pages
from app.routers import settings as settings_router
from app.routers import sources
from app.scheduler import shutdown as scheduler_shutdown
from app.scheduler import start as scheduler_start
from app.templating import TEMPLATES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("yt-sync-web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Make sure required directories exist
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    settings.archive_files_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    scheduler_start()
    log.info("startup complete — db ready, scheduler running")
    try:
        yield
    finally:
        scheduler_shutdown()
        log.info("shutdown complete")


app = FastAPI(title="yt-sync", lifespan=lifespan)

static_dir = TEMPLATES_DIR.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(pages.router)
app.include_router(sources.router)
app.include_router(downloads.router)
app.include_router(jobs.router)
app.include_router(oneoff.router)
app.include_router(settings_router.router)
