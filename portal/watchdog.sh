#!/usr/bin/env bash
# Restart the portal if it stops answering (covers crashes; not host reboots).
set -uo pipefail
P="$(cd "$(dirname "$0")" && pwd)"
while true; do
  if ! curl -s --max-time 3 -o /dev/null "http://127.0.0.1:${PORT:-8132}/api/health"; then
    "$P/run.sh" >> "$P/portal.log" 2>&1 &
  fi
  sleep 60
done
