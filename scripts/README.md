# Scripts

One-off analysis utilities (claims-map generation, figure scripts) live here once the campaign lands (E-P5/E-P6).

- `parity_check.py` — compare an instance's scenario results against a legacy reference table (`<instance>/results/parity/<label>-parity.{json,md}`); `--strict` exits non-zero on mismatches. See `planning/parity-reference-acquisition.md`.
- `campaign_birdmax.py` — maximum-bird endpoint solve (objective = bird abundance; even-flow on harvest); writes `<unit>-bmax` CSV + series JSON.
- `campaign_partition.py` — eleven-scenario bird partition (nadir to max; per-period floors, period 1 exempt); `--max-series` from `campaign_birdmax.py` or bisection fallback.
- `campaign_sensitivity.py` — even-flow epsilon / utilization sensitivity at matched bird targets (absolute floors from a baseline series).
- `frontier_analyze.py` — harvest/bird trade-off table from a directory of scenario CSVs.
