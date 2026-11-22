"""Controlled harvest experiment: identical schedules, two bird models.

No optimiser. A deterministic rule builds each schedule (oldest-first or random
selection, one clearcut per managed block, cuts spread evenly over 200 years), and
both anticipation models are evaluated on the *same* schedule and landscape.

Intensity is the share of managed area cut over the horizon; realized volume is an
output, not a target. This isolates the model question from harvest scheduling.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu python scripts/controlled_harvest.py \
      --dataset <compiled> --geometry <feather> --fits <spatial-local> \
      --tsa tsa41 --fractions 0.10 0.25 0.50 0.75 --order oldest random \
      --out dual/tsa41-controlled.csv
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import SpatialBird20  # noqa: E402

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
YEARS = 200


def build_schedule(blocks: list[int], area: np.ndarray, ages: np.ndarray,
                   fraction: float, order: str, rng: random.Random) -> dict[int, float]:
    """Assign one clearcut per selected block, spread evenly over the horizon."""
    ranked = sorted(blocks, key=lambda b: (-ages[b], b) if order == "oldest" else (rng.random(), b))
    total = float(area[ranked].sum())
    target = fraction * total
    selected: list[int] = []
    used = 0.0
    for block in ranked:
        if used >= target:
            break
        selected.append(block)
        used += float(area[block])
    n = len(selected)
    return {b: float(min(YEARS - 1, int(i * YEARS / n))) for i, b in enumerate(selected)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument("--tsa", required=True)
    parser.add_argument("--fractions", nargs="+", type=float, default=[0.10, 0.25, 0.50, 0.75])
    parser.add_argument("--order", nargs="+", default=["oldest", "random"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    import pickle

    with (args.dataset / "cache" / "candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    managed = [int(b) for b in index if index.get(b)]

    accounts = (HARVEST, STOCK, *[f"feature.Bird.{b}" for b in BIRDS])
    optimizer = Optimizer.from_dataset(
        args.dataset,
        OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1),
    )
    simulator = optimizer.simulator()
    all_blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(simulator, 200, accounts)
    fragments = pd.read_parquet(args.dataset / "fragments.parquet")
    area = fragments["area_ha"].to_numpy(float)
    ages = fragments["age"].to_numpy(float)

    base_state = BlockAccountState(trajectory, all_blocks, accounts, years=200, period_width=10, skip_empty=False)
    baseline = {b: float(base_state.period_totals[-1, accounts.index(f"feature.Bird.{b}")]) for b in BIRDS}
    print("aspatial baseline:", {k: round(v) for k, v in baseline.items()}, flush=True)

    spatial = SpatialBird20(args.dataset, args.geometry, args.fits)
    spatial_baseline = spatial.totals()
    print("spatial baseline:", {k: round(v) for k, v in spatial_baseline.items()}, flush=True)

    rows = []
    rng = random.Random(args.seed)
    for order in args.order:
        for fraction in args.fractions:
            schedule = build_schedule(managed, area, ages, fraction, order, rng)
            years = np.array(list(schedule.values()))
            base_state.set_schedule({b: (("CC", int(y)),) for b, y in schedule.items()})
            harvest = base_state.period_totals[:, accounts.index(HARVEST)]
            totals = spatial.rescore(schedule)
            cut_area = float(area[[int(b) for b in schedule]].sum())
            row = {
                "tsa": args.tsa,
                "order": order,
                "fraction": fraction,
                "blocks_cut": len(schedule),
                "area_cut_ha": round(cut_area, 1),
                "area_share": round(cut_area / float(area[managed].sum()), 4),
                "harvest_M_m3_yr": round(float(harvest.mean()) / 10 / 1e6, 4),
                "harvest_min_M": round(float(harvest.min()) / 1e6, 3),
                "harvest_max_M": round(float(harvest.max()) / 1e6, 3),
                "cut_age_median": round(float(np.median(ages[[int(b) for b in schedule]] + years)), 0),
            }
            for bird in BIRDS:
                i = accounts.index(f"feature.Bird.{bird}")
                a = float(base_state.period_totals[-1, i])
                s = float(totals[bird])
                row[f"{bird}_asp"] = round(a, 1)
                row[f"{bird}_sp"] = round(s, 1)
                row[f"{bird}_asp_pct"] = round(100.0 * (a - baseline[bird]) / baseline[bird], 2)
                row[f"{bird}_sp_pct"] = round(100.0 * (s - spatial_baseline[bird]) / spatial_baseline[bird], 2)
            rows.append(row)
            print(f"{order:6s} {fraction:.2f}: {len(schedule):,} blocks, {cut_area/1000:.0f}k ha, "
                  f"{row['harvest_M_m3_yr']:.3f} M m3/yr, median cut age {row['cut_age_median']:.0f}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
