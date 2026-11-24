#!/usr/bin/env bash
# Watch TSA41 against a single minimum harvest target at the TSR AAC.
# AAC 1,791,846 m3/yr x 10-year period = 17,918,460 m3 per period.
set -euo pipefail
W=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/ws4
C=/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11
OUT=${1:-/srv/shared-data/gep/wbi-birds/reference/wbi-main/runs/tsa41-aac-watch}
mkdir -p "$OUT"
"$W" state-watch \
  --dataset "$C/full-landscape/tsa41" \
  --targets /srv/shared-data/gep/wbi-birds/reference/wbi-main/targets/tsa41-aac.yaml \
  --candidate-index "$C/full-landscape/tsa41/cache/candidates.npz" \
  --initial-schedule "$C/prime/tsa41-prime.csv" \
  --years 200 --period-width 10 \
  --accounts "product.HarvestedVolume.managed.Total.CC" \
  --iterations "${ITERATIONS:-2000000}" \
  --schedule-out "$OUT/schedule.csv" \
  --summary-out "$OUT/summary.json"
