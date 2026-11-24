#!/usr/bin/env bash
# Watch TSA41 against a single minimum harvest target at the TSR AAC.
# AAC 1,791,846 m3/yr x 10-year period = 17,918,460 m3 per period.
set -euo pipefail
export PYTHONPATH="/srv/shared-data/gep/ws4/ws4-gpu${PYTHONPATH:+:$PYTHONPATH}"
W=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/ws4
PY=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python
C=/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11
INDEX="$C/full-landscape/tsa41/cache/candidates-nonempty.npz"
OUT=${1:-/srv/shared-data/gep/wbi-birds/reference/wbi-main/runs/tsa41-aac-watch}
mkdir -p "$OUT"
if [ ! -f "$INDEX" ]; then
  PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu "$PY" - "$C/full-landscape/tsa41/cache/candidates.npz" "$INDEX" <<'PYIDX'
import sys
from ws4.opt.model2_index import CandidateIndex
idx = CandidateIndex.load(sys.argv[1])
keep = {b: v for b, v in idx.to_candidates().items() if v}
CandidateIndex.build(keep).save(sys.argv[2])
PYIDX
fi
"$W" state-watch \
  --dataset "$C/full-landscape/tsa41" \
  --targets /srv/shared-data/gep/wbi-birds/reference/wbi-main/targets/tsa41-aac.yaml \
  --candidate-index "$INDEX" \
  --initial-schedule "$C/prime/tsa41-prime.csv" \
  --years 200 --period-width 10 \
  --accounts "product.HarvestedVolume.managed.Total.CC" \
  --iterations "${ITERATIONS:-2000000}" \
  --schedule-out "$OUT/schedule.csv" \
  --summary-out "$OUT/summary.json"
