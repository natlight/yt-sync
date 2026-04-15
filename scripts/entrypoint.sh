#!/bin/sh
# entrypoint.sh — wait for the PIA VPN sidecar (gluetun) to bring up tun0,
# then run sync.py. Checks /proc/net/dev for the tun0 interface rather than
# the gluetun HTTP API so there is no dependency on API auth configuration.
set -e

MAX_WAIT="${VPN_WAIT_TIMEOUT:-120}"
INTERVAL=5
elapsed=0

echo "========================================"
echo "Waiting for PIA VPN tunnel (tun0)"
echo "  timeout: ${MAX_WAIT}s"
echo "========================================"

while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    if grep -q 'tun0' /proc/net/dev 2>/dev/null; then
        echo "[vpn] tun0 is up after ${elapsed}s. Starting yt-sync."
        break
    fi

    echo "[vpn] tun0 not present yet (${elapsed}s elapsed). Retrying in ${INTERVAL}s..."
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

if ! grep -q 'tun0' /proc/net/dev 2>/dev/null; then
    echo "ERROR: VPN tunnel did not come up within ${MAX_WAIT}s. Aborting to avoid unprotected downloads."
    exit 1
fi

exec python /app/sync.py "$@"
