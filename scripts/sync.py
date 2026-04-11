#!/usr/bin/env python3
"""
yt-sync: Download new YouTube channel and playlist videos to Jellyfin.

Reads a YAML config (mounted via ConfigMap) listing channels and playlists.
Uses yt-dlp with SponsorBlock to remove ads/sponsor segments.
Tracks downloaded videos via archive files so re-runs only fetch new content.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml


def sanitize_name(name: str) -> str:
    """Make a name safe for use as a directory name."""
    # Replace characters that are problematic on most filesystems
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


def run_ytdlp(
    url: str,
    output_dir: str,
    archive_file: str,
    cookies_file: str | None = None,
    max_downloads: int = 20,
    label: str = "",
) -> int:
    """
    Run yt-dlp for a single source URL.

    Format strategy:
      1. Best MP4 video up to 4K + best M4A audio (most compatible with Jellyfin)
      2. Best video up to 4K + best audio (any container, merged to MP4)
      3. Single-file best quality fallback

    SponsorBlock removes: sponsor segments, self-promotion, interaction reminders,
    intros, outros, and preview/recap sections — effectively ad-free.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    output_template = os.path.join(output_dir, "%(upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s")

    cmd = [
        "yt-dlp",
        # Quality: prefer 4K MP4+M4A, fall back gracefully
        "--format",
        (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]"
            "/bestvideo[height<=2160]+bestaudio"
            "/best"
        ),
        "--merge-output-format", "mp4",
        # SponsorBlock: strip all non-content segments
        "--sponsorblock-remove",
        "sponsor,selfpromo,interaction,intro,outro,preview,music_offtopic",
        # Track downloads to avoid re-downloading
        "--download-archive", archive_file,
        # Output naming: date + title + video ID for uniqueness
        "--output", output_template,
        # Metadata & thumbnails embedded in the MP4
        "--embed-thumbnail",
        "--embed-metadata",
        "--convert-thumbnails", "jpg",
        # Skip live streams and ongoing broadcasts
        "--match-filter", "!is_live & !was_live",
        # Limit videos per run to avoid runaway jobs
        "--max-downloads", str(max_downloads),
        # Gracefully skip unavailable/private videos rather than aborting
        "--ignore-errors",
        # Retry network errors
        "--retries", "5",
        "--fragment-retries", "5",
        # Rate limiting to be a good citizen
        "--sleep-interval", "2",
        "--max-sleep-interval", "5",
    ]

    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", cookies_file])
        print(f"  [auth] Using cookies from {cookies_file}")
    else:
        print(f"  [auth] No cookies file found at {cookies_file} — public content only")

    cmd.append(url)

    print(f"  [cmd] yt-dlp {' '.join(cmd[1:])}")
    result = subprocess.run(cmd)

    # yt-dlp exit codes:
    #   0 = success
    #   1 = some errors occurred but download continued
    #   2 = critical error
    # We also see 101 when --max-downloads is hit (treated as success)
    return result.returncode


def main() -> None:
    config_file = os.getenv("CONFIG_FILE", "/config/sources.yaml")
    media_root = os.getenv("MEDIA_ROOT", "/media")
    archive_dir = os.getenv("ARCHIVE_DIR", "/archive")
    cookies_file = os.getenv("COOKIES_FILE", "/secrets/cookies.txt")
    max_downloads = int(os.getenv("MAX_DOWNLOADS_PER_SOURCE", "20"))

    print("=" * 60)
    print("yt-sync starting")
    print(f"  config:       {config_file}")
    print(f"  media root:   {media_root}")
    print(f"  archive dir:  {archive_dir}")
    print(f"  max per src:  {max_downloads}")
    print("=" * 60)

    # Ensure archive directory exists
    Path(archive_dir).mkdir(parents=True, exist_ok=True)

    # Load config
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_file}")
        sys.exit(1)

    channels = config.get("channels", [])
    playlists = config.get("playlists", [])

    if not channels and not playlists:
        print("WARNING: No channels or playlists configured. Nothing to do.")
        sys.exit(0)

    errors: list[str] = []

    # --- Channels ---
    for entry in channels:
        name = entry.get("name", "Unknown Channel")
        url = entry.get("url", "")
        if not url:
            print(f"SKIP: Channel '{name}' has no URL configured.")
            continue

        safe_name = sanitize_name(name)
        output_dir = os.path.join(media_root, "YouTube Channels", safe_name)
        archive_file = os.path.join(archive_dir, f"channel-{safe_name}.txt")

        print(f"\n>>> Channel: {name}")
        print(f"    url:     {url}")
        print(f"    output:  {output_dir}")

        rc = run_ytdlp(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies_file,
            max_downloads=max_downloads,
            label=name,
        )

        if rc not in (0, 1, 101):
            errors.append(f"Channel '{name}' failed with exit code {rc}")
        else:
            print(f"    [done] exit code {rc}")

    # --- Playlists / Watchlists ---
    for entry in playlists:
        name = entry.get("name", "Unknown Playlist")
        # Support either a full URL or just a playlist ID
        url = entry.get("url") or (
            f"https://www.youtube.com/playlist?list={entry['id']}"
            if entry.get("id")
            else ""
        )
        if not url:
            print(f"SKIP: Playlist '{name}' has no URL or id configured.")
            continue

        safe_name = sanitize_name(name)
        output_dir = os.path.join(media_root, "YouTube Playlists", safe_name)
        archive_file = os.path.join(archive_dir, f"playlist-{safe_name}.txt")

        print(f"\n>>> Playlist: {name}")
        print(f"    url:     {url}")
        print(f"    output:  {output_dir}")

        rc = run_ytdlp(
            url=url,
            output_dir=output_dir,
            archive_file=archive_file,
            cookies_file=cookies_file,
            max_downloads=max_downloads,
            label=name,
        )

        if rc not in (0, 1, 101):
            errors.append(f"Playlist '{name}' failed with exit code {rc}")
        else:
            print(f"    [done] exit code {rc}")

    # --- Summary ---
    print("\n" + "=" * 60)
    if errors:
        print("COMPLETED WITH ERRORS:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("All sources synced successfully.")


if __name__ == "__main__":
    main()
