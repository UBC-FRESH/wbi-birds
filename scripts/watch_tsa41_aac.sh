#!/usr/bin/env bash
# Watch the TSA41 AAC minimum-harvest target through FreshForge.
set -euo pipefail
ROOT=/srv/shared-data/gep/wbi-birds/reference/wbi-main
E=/srv/shared-data/gep/wbi-birds/wbi-birds/.venv/bin
cd "$ROOT"
"$E/freshforge" run workflows/tsa41_aac_watch.yaml --workdir . \
  --namespace tsa41-aac-watch --evidence results/workflow/tsa41-aac-watch/evidence.json &
pid=$!
trace="$ROOT/tsa41-aac-watch/results/workflow/tsa41-aac-watch/trace-level.jsonl"
while kill -0 "$pid" 2>/dev/null; do
  if [ -f "$trace" ]; then tail -n 3 "$trace"; fi
  sleep 30
done
wait "$pid"
cat "$ROOT/tsa41-aac-watch/results/workflow/tsa41-aac-watch/result.json" 2>/dev/null || true
