#!/usr/bin/env bash
# Serve the wbi-birds portal. Public host: wbi-birds.01101.dev -> this port.
set -euo pipefail
cd "$(dirname "$0")"
exec /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python server.py --host 0.0.0.0 --port "${PORT:-8132}"
