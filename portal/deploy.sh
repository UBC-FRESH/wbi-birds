#!/usr/bin/env bash
# Sync tracked portal source to the live service directory (generated data/tiles stay).
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${PORTAL_DEST:-/srv/shared-data/gep/jupyterhub16-projects/wbi-portal}"
rsync -a --exclude 'ui/data' --exclude 'ui/tiles' --exclude '*.log' --exclude '__pycache__' \
  "$SRC/" "$DEST/"
echo "synced $SRC -> $DEST"
