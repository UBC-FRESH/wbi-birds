"""Epsilon-constraint sweep with continuation and a full iteration budget.

Search is warm-started and chained: the first epsilon starts from a converged
harvest schedule, each next epsilon starts from the previous solution. Only the
accounts the objective needs are resident during search (harvest, stock, the
constrained bird); all nine birds are measured afterwards from the saved
schedules.

    PYTHONPATH=/srv/shared-data/gep/ws4/ws4-gpu \
      /srv/shared-data/gep/wbi-birds/tmp/ws4-env/bin/python \
      scripts/sweep_epsilon.py --dataset <compiled-bird> --bird gockin \
      --epsilons 1.05e6 1.15e6 1.25e6 --iterations 2000000 \
      --initial <converged schedule.csv> --out <csv>
"""
from __future__ import annotations

import argparse
import csv
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

BIRDS = ("rebnut", "borchi2", "gockin", "brncre", "yerwar", "swathr", "whtspa", "tenwar", "yebsap")
HARVEST = "product.HarvestedVolume.managed.Total.CC"
STOCK = "feature.Yield.managed.Total"
FULL_ACCOUNTS = (HARVEST, STOCK, *[f"feature.Bird.{s}" for s in BIRDS])


def target_yaml(bird: str, epsilon: float, pull: float, band: float) -> str:
    lines = ["targets:"]
    for period in range(1, 21):
        lines += [
            f"- account: {HARVEST}",
            "  period_width: 10",
            f"  minimum: {pull:.1f}",
            "  min_weight: 1.0",
            "  shape: linear",
            f"  period: {period}",
        ]
    lines += [
        f"- account: {HARVEST}",
        "  period: 1",
        "  period_width: 10",
        "  flow: even",
        "  flow_start_period: 1",
        "  flow_end_period: 20",
        "  flow_reference_period: 1",
        f"  minimum: {-band:.1f}",
        f"  maximum: {band:.1f}",
        "  min_weight: 10000.0",
        "  max_weight: 10000.0",
        "  shape: non_linear",
        f"- account: feature.Bird.{bird}",
        "  period: 20",
        "  period_width: 10",
        f"  minimum: {epsilon:.1f}",
        "  min_weight: 10000000.0",
        "  shape: non_linear",
    ]
    return "\n".join(lines) + "\n"


def write_schedule(schedule: dict, path: Path) -> None:
    rows = [
        {"block_id": block, "treatment": treatment, "offset": offset}
        for block, events in schedule.items()
        for treatment, offset in events
    ]
    pd.DataFrame(rows, columns=["block_id", "treatment", "offset"]).to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--bird", required=True, choices=BIRDS)
    parser.add_argument("--epsilons", nargs="+", type=float, required=True)
    parser.add_argument("--pull", type=float, default=40e6)
    parser.add_argument("--band", type=float, default=5.0)
    parser.add_argument("--iterations", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from ws4.opt.engine import OptimizeConfig, Optimizer, load_schedule_csv
    from ws4.opt.model2_trajectory import BlockAccountState, TrackTrajectory, run_state_sa
    from ws4.opt.objective import load_targets

    dataset = args.dataset
    with (dataset / "cache" / "candidates.pkl").open("rb") as stream:
        payload = pickle.load(stream)
    index = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    blocks = sorted(int(b) for b in index if index.get(b))

    optimizer = Optimizer.from_dataset(
        dataset,
        OptimizeConfig(
            years=200,
            targets_path=str(dataset / "targets-evenflow-steady-v7.yaml"),
            iterations=1,
            threads=1,
        ),
    )
    simulator = optimizer.simulator()
    search_accounts = (HARVEST, STOCK, f"feature.Bird.{args.bird}")
    search_trajectory = TrackTrajectory.build(simulator, 200, search_accounts)

    current = load_schedule_csv(args.initial)
    results = []
    schedules = {}
    for epsilon in args.epsilons:
        targets_file = Path(f"/tmp/opencode/eps-{args.bird}-{epsilon:.0f}.yaml")
        targets_file.write_text(target_yaml(args.bird, epsilon, args.pull, args.band))
        targets = load_targets(targets_file)
        started = time.perf_counter()
        state = BlockAccountState(
            search_trajectory, blocks, search_accounts, years=200, period_width=10, skip_empty=False
        )
        schedule, objective = run_state_sa(
            state, index, targets, iterations=args.iterations, initial=current, seed=args.seed
        )
        elapsed = time.perf_counter() - started
        harvest = state.period_totals[:, 0]
        bird_p20 = float(state.period_totals[-1, 2])
        row = {
            "bird": args.bird,
            "epsilon_p20": epsilon,
            "iterations": args.iterations,
            "seconds": round(elapsed, 1),
            "objective": round(float(objective), 1),
            "harvest_realized_m3_yr": round(float(harvest.mean()) / 10 / 1e6, 3),
            "harvest_min_M": round(float(harvest.min()) / 1e6, 3),
            "harvest_max_M": round(float(harvest.max()) / 1e6, 3),
            f"{args.bird}_p20": round(bird_p20, 1),
            "blocks_assigned": len(schedule),
        }
        results.append(row)
        schedules[epsilon] = dict(schedule)
        current = schedule
        print(
            f"eps {epsilon:.0f} -> harvest {row['harvest_realized_m3_yr']:.3f} M/yr "
            f"{args.bird}_p20 {bird_p20:.0f} obj {row['objective']:.3g} ({elapsed:.0f}s)",
            flush=True,
        )

    # Measure all nine birds afterwards, one load.
    full_trajectory = TrackTrajectory.build(simulator, 200, FULL_ACCOUNTS)
    for epsilon, schedule in schedules.items():
        state = BlockAccountState(
            full_trajectory, blocks, FULL_ACCOUNTS, years=200, period_width=10, skip_empty=False
        )
        state.set_schedule(schedule)
        totals = state.period_totals
        row = next(r for r in results if r["epsilon_p20"] == epsilon)
        for bird in BIRDS:
            values = totals[:, FULL_ACCOUNTS.index(f"feature.Bird.{bird}")]
            row[f"{bird}_mean"] = round(float(values.mean()), 1)
            row[f"{bird}_p20"] = round(float(values[-1]), 1)
        row["stock_p20_M"] = round(float(totals[-1, FULL_ACCOUNTS.index(STOCK)]) / 1e6, 1)
        write_schedule(schedule, args.out.with_name(f"{args.out.stem}-{epsilon:.0f}.csv"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
