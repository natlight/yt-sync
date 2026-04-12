#!/bin/sh
# entrypoint.sh — wait for the PIA VPN sidecar (gluetun) to connect, then run sync.py.
# If the VPN sidecar is not present (e.g. local dev), the health check times out and
# the script exits with an error rather than downloading without VPN protection.
set -e

VPN_STATUS_URL="http://localhost:8000/v1/vpn/status"
MAX_WAIT="${VPN_WAIT_TIMEOUT:-120}"
INTERVAL=5
elapsed=0

echo "========================================"
echo "Waiting for PIA VPN sidecar to connect"
echo "  endpoint: $VPN_STATUS_URL"
echo "  timeout:  ${MAX_WAIT}s"
echo "========================================"

while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    status=$(curl -sf "$VPN_STATUS_URL" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null \
        || true)

    if [ "$status" = "running" ]; then
        echo "[vpn] Connected. Starting yt-sync after ${elapsed}s."
        break
    fi

    echo "[vpn] Not ready yet (${elapsed}s elapsed, status='${status}'). Retrying in ${INTERVAL}s..."
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    echo "ERROR: VPN did not connect within ${MAX_WAIT}s. Aborting to avoid unprotected downloads."
    exit 1
fi

exec python /app/sync.py "$@"
