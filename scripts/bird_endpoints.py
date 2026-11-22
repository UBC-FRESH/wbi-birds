"""Bird endpoints for one dataset: no harvest vs a given schedule (period 20).

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/bird_endpoints.py --dataset <compiled-bird> [--schedule <csv>] --out <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
ACCOUNTS = (HARVEST, STOCK, *[f"feature.Bird.{s}" for s in BIRDS])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory

    dataset = args.dataset
    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    # Measure on the same population the search state covers: blocks that have
    # candidate chains.  TSA24 has 250k blocks without candidates; counting them
    # here while excluding them from the state made every epsilon infeasible.
    import pickle

    with (dataset / "cache" / "candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    blocks = sorted(int(b) for b in index if index.get(b))
    trajectory = TrackTrajectory.build(optimizer.simulator(), 200, ACCOUNTS)
    state = BlockAccountState(
        trajectory, blocks, ACCOUNTS, years=200, period_width=10, skip_empty=False
    )
    if args.schedule is not None:
        state.set_schedule(load_schedule_csv(args.schedule))
    totals = state.period_totals
    harvest = totals[:, 0]
    payload = {
        "dataset": str(dataset),
        "schedule": str(args.schedule) if args.schedule else None,
        "harvest_m3_yr": round(float(harvest.mean()) / 10 / 1e6, 3),
        "harvest_min_M": round(float(harvest.min()) / 1e6, 3),
        "harvest_max_M": round(float(harvest.max()) / 1e6, 3),
        "stock_p20_M": round(float(totals[-1, ACCOUNTS.index(STOCK)]) / 1e6, 1),
        "birds": {
            bird: {
                "mean": round(float(totals[:, ACCOUNTS.index(f"feature.Bird.{bird}")].mean()), 1),
                "p20": round(float(totals[-1, ACCOUNTS.index(f"feature.Bird.{bird}")]), 1),
            }
            for bird in BIRDS
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in payload.items() if k != "birds"}))
    for bird in BIRDS:
        print(f"  {bird:8s} p20 {payload['birds'][bird]['p20']:>12.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
