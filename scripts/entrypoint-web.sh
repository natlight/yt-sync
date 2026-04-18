#!/bin/sh
# entrypoint-web.sh — wait for the PIA VPN sidecar (gluetun) to bring up tun0
# AND for DNS to be working, then exec uvicorn for the web service.
#
# In local docker-compose without gluetun, set SKIP_VPN_WAIT=1 to bypass.
set -e

if [ "${SKIP_VPN_WAIT:-0}" = "1" ]; then
    echo "[web] SKIP_VPN_WAIT=1 — starting uvicorn immediately."
    exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}" "$@"
fi

MAX_WAIT="${VPN_WAIT_TIMEOUT:-180}"
INTERVAL=5
elapsed=0

echo "========================================"
echo "yt-sync-web: waiting for PIA VPN tunnel (tun0)"
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

echo "Waiting for DNS resolution (youtube.com)..."
while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if python3 -c "import socket; socket.getaddrinfo('youtube.com', 80)" 2>/dev/null; then
        echo "[dns] DNS ready after ${elapsed}s. Starting uvicorn."
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

exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}" "$@"
