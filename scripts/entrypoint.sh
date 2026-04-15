#!/bin/sh
# entrypoint.sh — wait for the PIA VPN sidecar (gluetun) to bring up tun0
# AND for DNS to be working, then run sync.py.
#
# Two-phase check:
#   1. tun0 interface present  → VPN tunnel is established
#   2. youtube.com resolves    → gluetun DNS server is ready (blocklist download done)
set -e

MAX_WAIT="${VPN_WAIT_TIMEOUT:-180}"
INTERVAL=5
elapsed=0

# ── Phase 1: wait for tun0 ──────────────────────────────────────────────────
echo "========================================"
echo "Waiting for PIA VPN tunnel (tun0)"
echo "  timeout: ${MAX_WAIT}s"
echo "========================================"

while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if grep -q 'tun0' /proc/net/dev 2>/dev/null; then
        echo "[vpn] tun0 is up after ${elapsed}s."
        break
    fi
    echo "[vpn] tun0 not present yet (${elapsed}s elapsed). Retrying in ${INTERVAL}s..."
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

if ! grep -q 'tun0' /proc/net/dev 2>/dev/null; then
    echo "ERROR: VPN tunnel did not come up within ${MAX_WAIT}s. Aborting."
    exit 1
fi

# ── Phase 2: wait for DNS ───────────────────────────────────────────────────
# gluetun's DNS server takes extra time after tun0 is up (downloads blocklists).
# Attempting to download before DNS works causes yt-dlp name resolution failures.
echo "Waiting for DNS resolution (youtube.com)..."

while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if python3 -c "import socket; socket.getaddrinfo('youtube.com', 80)" 2>/dev/null; then
        echo "[dns] DNS ready after ${elapsed}s. Starting yt-sync."
        break
    fi
    echo "[dns] DNS not ready yet (${elapsed}s elapsed). Retrying in ${INTERVAL}s..."
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

if ! python3 -c "import socket; socket.getaddrinfo('youtube.com', 80)" 2>/dev/null; then
    echo "ERROR: DNS did not become ready within ${MAX_WAIT}s. Aborting."
    exit 1
fi

exec python /app/sync.py "$@"
