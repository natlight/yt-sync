# Creating the yt-sync-cookies Secret

Private YouTube content (Watch Later, Liked Videos, members-only videos) requires
browser cookies for authentication. These are stored as a Kubernetes Secret and
mounted read-only into the CronJob container.

## Step 1 — Export cookies from your browser

Install the **"Get cookies.txt LOCALLY"** extension:
- Chrome: https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
- Firefox: search "cookies.txt" in the add-on store

1. Open YouTube and make sure you are signed in to the account whose playlists you want to download.
2. Click the extension icon and export cookies for `youtube.com`.
3. Save the file as `cookies.txt` (Netscape format — the extension handles this automatically).

> **Security note**: This file contains your session credentials. Never commit it to git.
> The `.gitignore` in this repo already excludes `cookies.txt`.

## Step 2 — Create the Kubernetes Secret

```bash
kubectl create secret generic yt-sync-cookies \
  --from-file=cookies.txt=./cookies.txt \
  --namespace media
```

Verify it was created:

```bash
kubectl get secret yt-sync-cookies -n media
```

## Step 3 — Rotate cookies when they expire

YouTube session cookies typically expire after a few months or when you sign out.
To refresh:

1. Export fresh cookies from your browser (Step 1).
2. Delete and recreate the secret:

```bash
kubectl delete secret yt-sync-cookies -n media
kubectl create secret generic yt-sync-cookies \
  --from-file=cookies.txt=./cookies.txt \
  --namespace media
```

The next CronJob run will automatically use the updated cookies.

## Public channels (no cookies needed)

If you only want to sync public YouTube channels, cookies are not required.
The `optional: true` flag on the secret volume mount means the job runs fine
even if the secret doesn't exist — it just logs a warning and skips private playlists.
