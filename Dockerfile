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

# Install yt-dlp + base CronJob deps
RUN pip install --no-cache-dir \
    yt-dlp \
    PyYAML \
    mutagen

# Web service deps (FastAPI/SQLModel/APScheduler/Jinja2/etc)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app

# Original CronJob assets (still used by k8s/cronjob.yaml during transition)
COPY scripts/sync.py /app/sync.py
COPY scripts/entrypoint.sh /app/entrypoint.sh

# Web service assets
COPY app/ /app/app/
COPY scripts/seed_from_yaml.py /app/scripts/seed_from_yaml.py
COPY scripts/entrypoint-web.sh /app/entrypoint-web.sh

RUN chmod +x /app/entrypoint.sh /app/entrypoint-web.sh

EXPOSE 8080

# Default to the web entrypoint. The CronJob overrides `command:` to use
# /app/entrypoint.sh so it keeps running the original sync.py flow.
ENTRYPOINT ["/app/entrypoint-web.sh"]
