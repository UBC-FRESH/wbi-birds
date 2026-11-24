#!/usr/bin/env bash
# Stage 1: AAC minimum harvest target, nonlinear, 1M.
# Stage 2: same AAC level as a linear penalty, even-flow +/-5% activated, 2M.
# Watches both stages live through the ws4 state-watch CLI.
set -uo pipefail
export PYTHONPATH="/srv/shared-data/gep/ws4/ws4-gpu${PYTHONPATH:+:$PYTHONPATH}"
W=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/ws4
PY=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python
C=/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11
T1=/srv/shared-data/gep/wbi-birds/reference/wbi-main/targets/tsa41-aac.yaml
INDEX="$C/full-landscape/tsa41/cache/candidates-nonempty.npz"
OUT=${1:-/srv/shared-data/gep/wbi-birds/reference/wbi-main/runs/tsa41-aac-staged}
ITER1=${ITER1:-1000000}
ITER2=${ITER2:-2000000}
LEVEL2=${LEVEL2:-17918460}
mkdir -p "$OUT"
T2="$OUT/stage2-target.yaml"
python3 - "$LEVEL2" "$T2" <<'PYTGT'
import sys
level=float(sys.argv[1]); out=sys.argv[2]
lines=["targets:"]
for p in range(1,21):
    lines += ["- account: product.HarvestedVolume.managed.Total.CC",
              "  period_width: 10", f"  minimum: {level:.1f}",
              "  min_weight: 1.0", "  shape: linear", f"  period: {p}"]
lines += ["- account: product.HarvestedVolume.managed.Total.CC",
          "  period: 1", "  period_width: 10", "  flow: even",
          "  flow_start_period: 1", "  flow_end_period: 20",
          "  minimum: -5.0", "  maximum: 5.0",
          "  min_weight: 1000000000.0", "  max_weight: 1000000000.0",
          "  shape: non_linear"]
open(out,"w").write("\n".join(lines)+"\n")
PYTGT
if [ ! -f "$INDEX" ]; then
  PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu "$PY" - "$C/full-landscape/tsa41/cache/candidates.npz" "$INDEX" <<'PYIDX'
import sys
from ws4.opt.model2_index import CandidateIndex
idx = CandidateIndex.load(sys.argv[1])
keep = {b: v for b, v in idx.to_candidates().items() if v}
CandidateIndex.build(keep).save(sys.argv[2])
PYIDX
fi
echo "=== stage 1: AAC nonlinear, ${ITER1} iterations ==="
"$W" state-watch \
  --dataset "$C/full-landscape/tsa41" --targets "$T1" \
  --candidate-index "$INDEX" --initial-schedule "$C/prime/tsa41-prime.csv" \
  --years 200 --period-width 10 \
  --accounts product.HarvestedVolume.managed.Total.CC \
  --iterations "$ITER1" \
  --schedule-out "$OUT/stage1-schedule.csv" \
  --summary-out "$OUT/stage1-summary.json"
rc1=$?
if [ "$rc1" -ne 0 ]; then
  echo "stage 1 state-watch exited $rc1; stopping before stage 2" >&2
  exit "$rc1"
fi
echo "=== stage 2: AAC linear + even-flow +/-5%, ${ITER2} iterations ==="
"$W" state-watch \
  --dataset "$C/full-landscape/tsa41" --targets "$T2" \
  --candidate-index "$INDEX" --initial-schedule "$OUT/stage1-schedule.csv" \
  --years 200 --period-width 10 \
  --accounts product.HarvestedVolume.managed.Total.CC \
  --iterations "$ITER2" \
  --schedule-out "$OUT/stage2-schedule.csv" \
  --summary-out "$OUT/stage2-summary.json"
