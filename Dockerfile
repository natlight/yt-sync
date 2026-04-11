FROM python:3.12-slim

# Install ffmpeg (required for merging video/audio streams) and AtomicParsley (for thumbnail embedding)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    atomicparsley \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (pinned to a stable release, update as needed)
RUN pip install --no-cache-dir \
    yt-dlp \
    PyYAML

COPY scripts/sync.py /app/sync.py

WORKDIR /app

ENTRYPOINT ["python", "sync.py"]
