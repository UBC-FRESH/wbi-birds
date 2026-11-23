#!/usr/bin/env bash
# Re-run the five-TSA dual campaign with the year-matched SCANFI 240 m AF.
#
# 40 points: five TSAs x four species x one seed, two attainments (0.85, 0.90).
# Each point is an independent single-core worker; the no-harvest baselines are
# precomputed in dual-scanfi-240m/tsa<id>-baselines.json.
set -uo pipefail
C=/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11
PY=/srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python
OUTDIR="$C/dual-scanfi-240m"
FITS="$C/bird-fits/scanfi-240m-nine-species-spatial.json"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu
cd /srv/shared-data/gep/wbi-birds/reference/wbi-main
mkdir -p "$OUTDIR"

geom() {
  echo "/srv/shared-data/gep/wbi-birds/femic/external/femic-tsa$1-instance/data/ria_vri_vclr1p_checkpoint7.feather"
}

is_complete() {
  "$PY" - "$1" <<'PYCHECK'
import csv, sys
try:
    rows = list(csv.DictReader(open(sys.argv[1])))
except Exception:
    sys.exit(1)
by_mode = {}
for row in rows:
    by_mode.setdefault(row.get("mode"), set()).add(row.get("epsilon_p20"))
ok = len(by_mode) >= 2 and all(len(v) >= 2 for v in by_mode.values())
sys.exit(0 if ok else 1)
PYCHECK
}

for T in 41 40 24 08 16; do
  for BIRD in borchi2 gockin yerwar whtspa; do
    OUT="$OUTDIR/tsa$T-multi-s42-${BIRD}.csv"
    if is_complete "$OUT"; then
      echo "skip complete $OUT" >> "$OUTDIR/tsa$T-campaign.log"
      continue
    fi
    "$PY" scripts/dual_campaign.py \
      --dataset "$C/full-landscape/tsa$T" --geometry "$(geom "$T")" \
      --fits "$FITS" --tsa "tsa$T" \
      --bird "$BIRD" --attainments 0.85 0.90 --iterations 300000 --seed 42 \
      --prime "$C/prime/tsa$T-prime.csv" --out "$OUT" \
      >> "$OUTDIR/tsa$T-campaign.log" 2>&1 &
  done
done
wait
echo "scanfi campaign done $(date -u +%FT%TZ)"
