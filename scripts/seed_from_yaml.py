"""Seed the SQLite DB from the existing sources.yaml ConfigMap.

Run once during the migration from CronJob to web service. Imported sources
default to enabled=False so they don't collide with the still-running CronJob.
Re-running is safe: rows are matched by (type, url) and skipped if present.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from sqlmodel import Session, select

# Allow running both as a module (python -m scripts.seed_from_yaml) and a script
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import engine, init_db  # noqa: E402
from app.models import Source, SourceType  # noqa: E402


def _resolve_url(entry: dict, base_url: str) -> str:
    return entry.get("url") or (
        f"{base_url}{entry['id']}" if entry.get("id") else ""
    )


def seed_from_yaml(yaml_path: Path, *, default_max: int = 25) -> dict[str, int]:
    init_db()
    with open(yaml_path) as f:
        config = yaml.safe_load(f) or {}

    inserted = {"channel": 0, "playlist": 0, "music": 0, "skipped": 0}

    sections = [
        ("channels", SourceType.channel, ""),
        ("playlists", SourceType.playlist, "https://www.youtube.com/playlist?list="),
        ("music_playlists", SourceType.music, "https://music.youtube.com/playlist?list="),
    ]

    with Session(engine) as session:
        for key, type_, base in sections:
            for entry in (config.get(key) or []):
                url = _resolve_url(entry, base)
                name = entry.get("name", "Unknown")
                if not url:
                    continue
                exists = session.exec(
                    select(Source).where(Source.type == type_, Source.url == url)
                ).first()
                if exists is not None:
                    inserted["skipped"] += 1
                    continue
                src = Source(
                    type=type_,
                    name=name,
                    url=url,
                    cron=None,
                    enabled=False,
                    max_downloads=default_max,
                    date_after=entry.get("date_after"),
                )
                session.add(src)
                inserted[type_.value] += 1
        session.commit()

    return inserted


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/config/sources.yaml")
    counts = seed_from_yaml(path)
    print(f"Imported from {path}: {counts}")
