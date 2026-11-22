"""Same-schedule harvest impact for all nine species, both models.

Holds management fixed (a converged even-flow schedule) and evaluates each model
on the same full landscape, so the comparison isolates the response model.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu python scripts/dual_impact.py \
      --dataset <compiled> --geometry <feather> --fits <spatial-local> \
      --prime <prime.csv> --tsa tsa41 --out dual/tsa41-impact.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_model20 import YEAR, SpatialBird20  # noqa: E402

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"


def p20_schedule(schedule: dict) -> dict[int, float]:
    out = {}
    for block, chain in schedule.items():
        years = [int(year) for _treatment, year in chain if year <= YEAR]
        if years:
            out[int(block)] = float(max(years))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument("--prime", type=Path, required=True)
    parser.add_argument("--tsa", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    accounts = (HARVEST, STOCK, *[f"feature.Bird.{b}" for b in BIRDS])
    optimizer = Optimizer.from_dataset(
        args.dataset,
        OptimizeConfig(years=200, targets_path="/tmp/opencode/targets-level40.yaml", iterations=1, threads=1),
    )
    simulator = optimizer.simulator()
    blocks = sorted(int(b) for b in simulator.fragments["block_id"].unique())
    trajectory = TrackTrajectory.build(simulator, 200, accounts)
    schedule = load_schedule_csv(args.prime)

    def aspatial(with_schedule: bool):
        state = BlockAccountState(trajectory, blocks, accounts, years=200, period_width=10, skip_empty=False)
        if with_schedule:
            state.set_schedule(schedule)
        return state.period_totals

    base = aspatial(False)
    harvested = aspatial(True)
    harvest_rate = float(harvested[:, 0].mean()) / 10 / 1e6
    print(f"{args.tsa}: {harvest_rate:.3f} M m3/yr")

    rows = []
    for bird in BIRDS:
        i = accounts.index(f"feature.Bird.{bird}")
        a0, a1 = float(base[-1, i]), float(harvested[-1, i])
        model0 = SpatialBird20(args.dataset, args.geometry, args.fits, species=bird)
        s0 = float(model0.totals()[bird])
        model1 = SpatialBird20(args.dataset, args.geometry, args.fits, species=bird)
        model1.schedule = p20_schedule(schedule)
        model1.rebuild()
        s1 = float(model1.totals()[bird])
        rows.append({
            "tsa": args.tsa,
            "species": bird,
            "harvest_M_m3_yr": round(harvest_rate, 3),
            "aspatial_base": round(a0, 1),
            "aspatial_harvest": round(a1, 1),
            "aspatial_pct": round(100.0 * (a1 - a0) / a0, 2),
            "spatial_base": round(s0, 1),
            "spatial_harvest": round(s1, 1),
            "spatial_pct": round(100.0 * (s1 - s0) / s0, 2),
            "sign_flip": (a1 - a0) * (s1 - s0) < 0,
        })
        print(f"  {bird:8s} aspatial {100*(a1-a0)/a0:7.1f}%  spatial {100*(s1-s0)/s0:7.1f}%"
              f"{'  SIGN FLIP' if rows[-1]['sign_flip'] else ''}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
