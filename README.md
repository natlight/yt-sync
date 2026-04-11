# yt-sync

A Kubernetes CronJob that uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to sync YouTube channels and playlists to your Jellyfin media server automatically.

**Features:**
- Downloads new videos from YouTube channels and playlists on a schedule
- Each channel and playlist gets its own folder in Jellyfin
- Best available quality up to 4K (prefers MP4+M4A for Jellyfin compatibility)
- SponsorBlock integration removes sponsors, intros, outros, and self-promo segments
- Tracks downloaded videos so only new content is fetched each run
- Supports private playlists (Watch Later, Liked Videos) via browser cookies
- All sensitive data stored in Kubernetes Secrets

## Architecture

```
NAS (192.168.50.187)
└── /mnt/server/media/videos/
    ├── YouTube Channels/
    │   ├── Linus Tech Tips/
    │   │   └── 2024-03-15 My Video Title [dQw4w9WgXcQ].mp4
    │   └── Veritasium/
    └── YouTube Playlists/
        ├── Watch Later/
        └── My Playlist/
```

The NFS share is mounted as a dedicated PV/PVC and is independent of Jellyfin's own PVC — no sharing conflicts. Jellyfin simply scans the `YouTube Channels` and `YouTube Playlists` folders as part of its Videos library.

## Prerequisites

- Kubernetes cluster with the `media` namespace
- NFS server at `192.168.50.187` with `/mnt/server/media/videos` path accessible
- Container registry to push the image (repo uses `ghcr.io/natlight/yt-sync`)

## Setup

### 1. Build and push the image

```bash
cd /path/to/yt-sync

docker build -t ghcr.io/natlight/yt-sync:latest .
docker push ghcr.io/natlight/yt-sync:latest
```

Or use GitHub Actions (add a workflow that builds on push to main).

### 2. Configure channels and playlists

Edit [`k8s/configmap.yaml`](k8s/configmap.yaml) and add your channels/playlists:

```yaml
channels:
  - name: "Linus Tech Tips"
    url: "https://www.youtube.com/@LinusTechTips"

playlists:
  - name: "Watch Later"
    id: "WL"
```

### 3. (Optional) Create the cookies secret for private playlists

See [`k8s/secret-instructions.md`](k8s/secret-instructions.md) for full details.

```bash
kubectl create secret generic yt-sync-cookies \
  --from-file=cookies.txt=./cookies.txt \
  --namespace media
```

### 4. Deploy

```bash
# Create the NFS PersistentVolume (cluster-scoped, run once)
kubectl apply -f k8s/pv.yaml

# Create PVCs, ConfigMap, and CronJob
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/cronjob.yaml
```

### 5. Test with a manual run

Trigger a one-off job to verify everything is working before waiting for the schedule:

```bash
kubectl create job yt-sync-test \
  --from=cronjob/yt-sync \
  --namespace media

# Watch the logs
kubectl logs -f -l job-name=yt-sync-test -n media

# Clean up test job
kubectl delete job yt-sync-test -n media
```

### 6. Add Jellyfin library

In Jellyfin, add a **Videos** library pointing to:
- `/media/YouTube Channels` — for channel content
- `/media/YouTube Playlists` — for playlist/watchlist content

## Configuration reference

| Environment Variable | Default | Description |
|---|---|---|
| `CONFIG_FILE` | `/config/sources.yaml` | Path to the sources YAML (from ConfigMap) |
| `MEDIA_ROOT` | `/media` | Root path where channel/playlist folders are created |
| `ARCHIVE_DIR` | `/archive` | Path for download archive files (persisted in PVC) |
| `COOKIES_FILE` | `/secrets/cookies.txt` | Path to YouTube cookies file (from Secret) |
| `MAX_DOWNLOADS_PER_SOURCE` | `25` | Max new videos to download per channel/playlist per run |

## Updating channels/playlists

Edit the ConfigMap and apply — no restart needed, picked up on the next run:

```bash
kubectl apply -f k8s/configmap.yaml
```

## Troubleshooting

**View recent job logs:**
```bash
kubectl logs -n media -l app=yt-sync --tail=100
```

**Check CronJob status:**
```bash
kubectl get cronjob yt-sync -n media
kubectl get jobs -n media -l app=yt-sync
```

**Force a manual sync:**
```bash
kubectl create job yt-sync-manual \
  --from=cronjob/yt-sync \
  --namespace media
```

**Re-download everything (reset archive):**
```bash
kubectl exec -n media <archive-pod> -- rm /archive/*.txt
```
Or delete and recreate the `yt-sync-archive-pvc`.
