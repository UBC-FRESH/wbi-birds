"""Tradeoff sweep for one compiled dataset: harvest level x nine bird indicators.

For each harvest level it runs the resident SA with a linear level pull and an
even-flow band, starting from the untreated forest state, and records the
realized profile, growing stock, and every bird account.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/sweep_state_sa.py --dataset <compiled-bird> \
      --levels 1.2 1.6 2.0 2.4 2.8 3.2 --iterations 200000 \
      --out /tmp/tsa41-sweep.csv
"""
from __future__ import annotations

import argparse
import csv
import pickle
import time
from pathlib import Path

import numpy as np

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
ACCOUNTS = (HARVEST, STOCK, *[f"feature.Bird.{s}" for s in BIRDS])


def target_yaml(level_period: float, band: float, period_width: int = 10) -> str:
    lines = ["targets:"]
    for period in range(1, 21):
        lines += [
            f"- account: {HARVEST}",
            f"  period_width: {period_width}",
            f"  minimum: {level_period:.1f}",
            f"  maximum: {level_period:.1f}",
            "  min_weight: 1.0",
            "  max_weight: 10.0",
            "  shape: linear",
            f"  period: {period}",
        ]
    lines += [
        f"- account: {HARVEST}",
        "  period: 1",
        f"  period_width: {period_width}",
        "  flow: even",
        "  flow_start_period: 1",
        "  flow_end_period: 20",
        "  flow_reference_period: 1",
        f"  minimum: {-band:.1f}",
        f"  maximum: {band:.1f}",
        "  min_weight: 10000.0",
        "  max_weight: 10000.0",
        "  shape: non_linear",
    ]
    return "\n".join(lines) + "\n"


def build_trajectory(dataset: Path):
    from ws4.opt.engine import OptimizeConfig, Optimizer
    from ws4.opt.model2_trajectory import TrackTrajectory

    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    return TrackTrajectory.build(optimizer.simulator(), 200, ACCOUNTS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--levels", nargs="+", type=float, required=True)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--iterations", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import load_schedule_csv
    from ws4.opt.model2_trajectory import run_state_sa
    from ws4.opt.objective import load_targets

    initial = load_schedule_csv(args.initial) if args.initial is not None else None

    dataset = args.dataset
    candidates_path = args.candidates or dataset / "cache" / "candidates.pkl"
    with candidates_path.open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    blocks = sorted(int(b) for b in index if index.get(b))
    print(f"blocks with candidates: {len(blocks):,}", flush=True)

    from ws4.opt.model2_trajectory import BlockAccountState

    trajectory = build_trajectory(dataset)
    rows = []
    for level in args.levels:
        level_period = level * 1e6 * 10.0
        targets_file = Path(f"/tmp/opencode/sweep-target-{level:.1f}.yaml")
        targets_file.parent.mkdir(parents=True, exist_ok=True)
        targets_file.write_text(target_yaml(level_period, args.band))
        targets = load_targets(targets_file)

        started = time.perf_counter()
        state = BlockAccountState(
            trajectory, blocks, ACCOUNTS, years=200, period_width=10, skip_empty=False
        )
        schedule, objective = run_state_sa(
            state, index, targets, iterations=args.iterations, initial=initial, seed=args.seed
        )
        elapsed = time.perf_counter() - started
        totals = state.period_totals
        harvest = totals[:, ACCOUNTS.index(HARVEST)]
        stock = totals[:, ACCOUNTS.index(STOCK)]
        row = {
            "level_m3_yr": level,
            "iterations": args.iterations,
            "seconds": round(elapsed, 1),
            "objective": round(float(objective), 1),
            "harvest_mean_M": round(float(harvest.mean()) / 1e6, 3),
            "harvest_min_M": round(float(harvest.min()) / 1e6, 3),
            "harvest_max_M": round(float(harvest.max()) / 1e6, 3),
            "harvest_realized_m3_yr": round(float(harvest.mean()) / 10 / 1e6, 3),
            "stock_period20_M": round(float(stock[-1]) / 1e6, 1),
            "blocks_assigned": len(schedule),
        }
        for bird in BIRDS:
            values = totals[:, ACCOUNTS.index(f"feature.Bird.{bird}")]
            row[f"{bird}_mean"] = round(float(values.mean()), 1)
            row[f"{bird}_p20"] = round(float(values[-1]), 1)
        rows.append(row)
        print(
            f"level {level:.1f}M/yr -> realized {row['harvest_realized_m3_yr']:.3f} "
            f"stock20 {row['stock_period20_M']}M obj {row['objective']:.3g} "
            f"({elapsed:.0f}s)",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
