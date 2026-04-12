FROM python:3.12-slim

# Install ffmpeg (required for merging video/audio streams), AtomicParsley (for thumbnail
# embedding), and curl (used by entrypoint.sh to poll the gluetun VPN health endpoint).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    atomicparsley \
    ca-certificates \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (pinned to a stable release, update as needed)
RUN pip install --no-cache-dir \
    yt-dlp \
    PyYAML \
    mutagen

COPY scripts/sync.py /app/sync.py
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

WORKDIR /app

# entrypoint.sh waits for the PIA VPN sidecar (gluetun) to connect before running sync.py.
ENTRYPOINT ["/app/entrypoint.sh"]
